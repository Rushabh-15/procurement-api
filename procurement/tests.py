from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import Supplier, PurchaseOrder, GoodsReceiptNote, Invoice
from .services import run_three_way_match, get_overdue_invoices
from rest_framework.test import APITestCase
from rest_framework import status as http_status
from datetime import date, timedelta
from .services import parse_invoice_text, classify_invoice_category


User = get_user_model()


class ThreeWayMatchTests(TestCase):
    """
    Tests for the 3-way match service function.
    These are pure unit tests — no HTTP, no client.
    setUp() runs before EVERY test method automatically.
    """

    def setUp(self):
        # Create minimal test data — reused by every test in this class
        self.user = User.objects.create_user(username='testuser', password='pass')
        self.supplier = Supplier.objects.create(
            name='Test Supplier', email='test@supplier.com'
        )
        self.po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            created_by=self.user,
            status=PurchaseOrder.Status.APPROVED,
            total_amount=Decimal('10000.00')
        )
        self.grn = GoodsReceiptNote.objects.create(
            purchase_order=self.po,
            received_by=self.user,
            received_amount=Decimal('10000.00')
        )

    def _make_invoice(self, amount, number='INV-001'):
        """Helper: create an invoice without triggering match automatically."""
        from datetime import date, timedelta
        return Invoice.objects.create(
            purchase_order=self.po,
            invoice_number=number,
            amount=Decimal(str(amount)),
            due_date=date.today() + timedelta(days=30)
        )

    # ── HAPPY PATH ─────────────────────────────────────────────────────────

    def test_exact_match_returns_matched(self):
        """When all three amounts are identical, status must be MATCHED."""
        invoice = self._make_invoice(10000.00)
        result  = run_three_way_match(invoice)
        self.assertEqual(result, Invoice.MatchStatus.MATCHED)
        invoice.refresh_from_db()
        self.assertEqual(invoice.match_status, Invoice.MatchStatus.MATCHED)

    def test_within_tolerance_returns_matched(self):
        """Invoice within 5% of PO amount must still be MATCHED."""
        invoice = self._make_invoice(10400.00)  # 4% above — within tolerance
        result  = run_three_way_match(invoice)
        self.assertEqual(result, Invoice.MatchStatus.MATCHED)

    def test_matched_invoice_closes_purchase_order(self):
        """A successful match must auto-close the PO."""
        invoice = self._make_invoice(10000.00)
        run_three_way_match(invoice)
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, PurchaseOrder.Status.CLOSED)

    # ── DISCREPANCY CASES ──────────────────────────────────────────────────

    def test_invoice_above_tolerance_returns_discrepancy(self):
        """Invoice 10%+ above PO amount must be DISCREPANCY."""
        invoice = self._make_invoice(11500.00)  # 15% above — exceeds 5% tolerance
        result  = run_three_way_match(invoice)
        self.assertEqual(result, Invoice.MatchStatus.DISCREPANCY)

    def test_invoice_below_tolerance_returns_discrepancy(self):
        """Invoice significantly below PO amount is also a discrepancy."""
        invoice = self._make_invoice(8000.00)  # 20% below
        result  = run_three_way_match(invoice)
        self.assertEqual(result, Invoice.MatchStatus.DISCREPANCY)

    def test_discrepancy_does_not_close_po(self):
        """PO must remain APPROVED if the match is a discrepancy."""
        invoice = self._make_invoice(15000.00)
        run_three_way_match(invoice)
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, PurchaseOrder.Status.APPROVED)

    # ── EDGE CASES ─────────────────────────────────────────────────────────

    def test_no_grn_raises_validation_error(self):
        """Match without a GRN must raise ValidationError — not silently fail."""
        self.grn.delete()
        invoice = self._make_invoice(10000.00, number='INV-002')
        with self.assertRaises(ValidationError):
            run_three_way_match(invoice)

    def test_grn_mismatch_returns_discrepancy(self):
        """Even if the invoice matches, GRN mismatch causes DISCREPANCY."""
        self.grn.received_amount = Decimal('5000.00')   # GRN is only half the PO
        self.grn.save()
        invoice = self._make_invoice(10000.00, number='INV-003')
        result  = run_three_way_match(invoice)
        self.assertEqual(result, Invoice.MatchStatus.DISCREPANCY)


# API(Integration) tests go here — 
# they use the test client to make HTTP requests to the views.

class SupplierAPITests(APITestCase):
    """
    APITestCase extends TestCase and adds self.client — a test HTTP client.
    self.client.get/post/put/patch/delete — no server needed.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='apiuser', password='pass')
        self.client.force_authenticate(user=self.user)
        # force_authenticate bypasses JWT for tests — you're testing the view, not auth

    def test_create_supplier_returns_201(self):
        response = self.client.post('/api/suppliers/', {
            'name': 'HDFC Bank', 'email': 'vendor@hdfc.com'
        }, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'HDFC Bank')

    def test_list_suppliers_requires_auth(self):
        self.client.logout()
        self.client.force_authenticate(user=None)  # unauthenticate
        response = self.client.get('/api/suppliers/')
        self.assertEqual(response.status_code, http_status.HTTP_401_UNAUTHORIZED)

    def test_create_supplier_missing_email_returns_400(self):
        response = self.client.post('/api/suppliers/', {
            'name': 'No Email Corp'
        }, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)  # error must name the field

    def test_supplier_list_is_paginated(self):
        # Create 12 suppliers — more than PAGE_SIZE of 10
        for i in range(12):
            Supplier.objects.create(name=f'Supplier {i}', email=f's{i}@test.com')
        response = self.client.get('/api/suppliers/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('count', response.data)
        self.assertIn('next', response.data)     # pagination 'next' link exists
        self.assertEqual(len(response.data['results']), 10)  # first page = 10


class PurchaseOrderApproveTests(APITestCase):

    def setUp(self):
        self.user     = User.objects.create_user(username='pouser', password='pass')
        self.client.force_authenticate(user=self.user)
        self.supplier = Supplier.objects.create(
            name='Test Co', email='t@test.com', is_verified=True
        )
        self.po = PurchaseOrder.objects.create(
            supplier=self.supplier, created_by=self.user,
            total_amount=Decimal('5000.00')
        )

    def test_approve_draft_po_returns_200(self):
        response = self.client.post(f'/api/purchase-orders/{self.po.id}/approve/')
        self.assertEqual(response.status_code, 200)
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, PurchaseOrder.Status.APPROVED)

    def test_approve_already_approved_po_returns_400(self):
        self.po.status = PurchaseOrder.Status.APPROVED
        self.po.save()
        response = self.client.post(f'/api/purchase-orders/{self.po.id}/approve/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.data)

class InvoiceParserTests(TestCase):
    """Unit tests for the NLP parser — no DB, no HTTP, pure function testing."""

    CLEAN_INVOICE = (
        "Invoice from Tata Steel Ltd for Rs. 45,000 due 2024-03-31. "
        "Reference: INV-TATA-2024-001. Steel rods and materials."
    )
    MESSY_INVOICE = "pls pay ₹12500 by next week thanks"
    SERVICES_INVOICE = "Software consulting and support services license fee Rs. 80000 INV-SVC-001"

    def test_clean_invoice_vendor_is_high_confidence(self):
        result = parse_invoice_text(self.CLEAN_INVOICE)
        self.assertEqual(result['vendor']['confidence'], 'HIGH')
        self.assertIsNotNone(result['vendor']['value'])

    def test_clean_invoice_amount_extracted(self):
        result = parse_invoice_text(self.CLEAN_INVOICE)
        self.assertEqual(result['amount']['confidence'], 'HIGH')
        self.assertIn('45000', result['amount']['value'])

    def test_clean_invoice_date_extracted(self):
        result = parse_invoice_text(self.CLEAN_INVOICE)
        self.assertEqual(result['due_date']['value'], '2024-03-31')
        self.assertEqual(result['due_date']['confidence'], 'HIGH')

    def test_clean_invoice_number_extracted(self):
        result = parse_invoice_text(self.CLEAN_INVOICE)
        self.assertIsNotNone(result['invoice_number']['value'])
        self.assertIn('INV', result['invoice_number']['value'])

    def test_clean_invoice_does_not_require_review(self):
        result = parse_invoice_text(self.CLEAN_INVOICE)
        self.assertFalse(result['requires_review'])

    def test_messy_invoice_requires_review(self):
        result = parse_invoice_text(self.MESSY_INVOICE)
        self.assertTrue(result['requires_review'])

    def test_goods_invoice_classified_correctly(self):
        self.assertEqual(classify_invoice_category(self.CLEAN_INVOICE), 'GOODS')

    def test_services_invoice_classified_correctly(self):
        self.assertEqual(classify_invoice_category(self.SERVICES_INVOICE), 'SERVICES')

    def test_empty_text_still_returns_structure(self):
        """Parser must never crash — always return the full dict structure."""
        result = parse_invoice_text('')
        self.assertIn('vendor', result)
        self.assertIn('amount', result)
        self.assertTrue(result['requires_review'])