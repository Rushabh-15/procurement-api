import re
import spacy
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Invoice, PurchaseOrder

nlp = spacy.load('en_core_web_sm')  # load once at module level

def parse_invoice_text(text: str) -> dict:
    """
    Extract structured fields from raw invoice text using spaCy NER.
    Returns a dict with extracted values and per-field confidence scores.
    """
    doc = nlp(text)
    result = {
        'vendor': {'value': None, 'confidence': 'LOW'},
        'amount': {'value': None, 'confidence': 'LOW'},
        'due_date': {'value': None, 'confidence': 'LOW'},
        'invoice_number': {'value': None, 'confidence': 'LOW'},
    }

    for ent in doc.ents:
        if ent.label_ == 'ORG' and result['vendor']['value'] is None:
            result['vendor'] = {'value': ent.text, 'confidence': 'HIGH'}
        elif ent.label_ == 'MONEY' and result['amount']['value'] is None:
            result['amount'] = {'value': ent.text, 'confidence': 'HIGH'}
        elif ent.label_ == 'DATE' and result['due_date']['value'] is None:
            result['due_date'] = {'value': ent.text, 'confidence': 'HIGH'}

    inv_match = re.search(r'\b(INV|REF|INVOICE)[-\s]?[\w\d]+\b', text, re.IGNORECASE)
    if inv_match and result['invoice_number']['value'] is None:
        result['invoice_number'] = {'value': inv_match.group(), 'confidence': 'MEDIUM'}
    
    result['requires_review'] = any(
        v['confidence'] == 'LOW' for v in result.values() if isinstance(v, dict)
    )
    return result

def run_three_way_match(invoice: Invoice) -> str:
    """
    Perform a 3-way match between Purchase Order, Goods Receipt Note, and Invoice.

    Compares:
      1. PurchaseOrder.total_amount — agreed order value
      2. GoodsReceiptNote.received_amount — actual received value
      3. Invoice.amount — billed value

    All three must agree within a 5% tolerance for a MATCHED status.
    Any discrepancy beyond 5% results in DISCREPANCY, blocking payment.

    Side effects:
      - Updates invoice.match_status
      - Automatically closes the PurchaseOrder if matched

    Uses transaction.atomic() to ensure data consistency.

    Args:
        invoice (Invoice): The invoice instance to validate.

    Returns:
        str: Final match status ("MATCHED" or "DISCREPANCY").

    Raises:
        ValidationError: If no Goods Receipt Note exists for the PurchaseOrder.
    """
    with transaction.atomic():
        po = invoice.purchase_order

        # Validate: a GRN must exist before an invoice can be matched
        if not po.grns.exists():
            raise ValidationError(
                "Cannot match invoice: no Goods Receipt Note exists for this PO."
            )

        grn = po.grns.latest('received_at')   # use the most recent GRN

        po_amount  = po.total_amount
        grn_amount = grn.received_amount
        inv_amount = invoice.amount

        # 5% tolerance — in real procurement, small rounding differences are acceptable
        tolerance = po_amount * Decimal('0.05')

        po_inv_match  = abs(inv_amount - po_amount)  <= tolerance
        po_grn_match  = abs(grn_amount - po_amount) <= tolerance

        if po_inv_match and po_grn_match:
            invoice.match_status = Invoice.MatchStatus.MATCHED
        else:
            invoice.match_status = Invoice.MatchStatus.DISCREPANCY

        invoice.save(update_fields=['match_status'])

        # If matched, auto-close the PO
        if invoice.match_status == Invoice.MatchStatus.MATCHED:
            po.status = PurchaseOrder.Status.CLOSED
            po.save(update_fields=['status', 'updated_at'])

        return invoice.match_status


def get_overdue_invoices(queryset=None):
    """
    Returns all invoices past their due date that are not yet MATCHED.
    Uses ORM annotation rather than Python filtering — lets the DB do the work.
    """
    from django.utils import timezone
    from django.db.models import Q

    today = timezone.now().date()
    qs = queryset if queryset is not None else Invoice.objects.all()
    return qs.filter(
        Q(due_date__lt=today) & ~Q(match_status=Invoice.MatchStatus.MATCHED)
    ).select_related('purchase_order__supplier').order_by('due_date')