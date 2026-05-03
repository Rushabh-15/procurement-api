import re
import spacy
from decimal import Decimal
from django.db import transaction
from django.db.models import QuerySet
from django.core.exceptions import ValidationError
from .models import Invoice, PurchaseOrder
from spacy.matcher import Matcher
from typing import Dict, Any, List, Literal, Optional
from spacy.tokens import Doc
import pdfplumber
import io
import logging

logger = logging.getLogger(__name__)

# Load once at module level — critical for performance
nlp = spacy.load('en_core_web_sm')

# PhraseMatcher for known Indian enterprise vendor names
# In production this list comes from your Supplier database
KNOWN_VENDORS = [
    'Tata Steel', 'Reliance Industries', 'Infosys',
    'Wipro', 'Mahindra', 'HDFC Bank', 'Bajaj Auto',
]

# Compile regex patterns once — not inside the function
INVOICE_NUM_RE = re.compile(
    r'\b(INV|INVOICE|REF|BILL)[-/\s]?[\w\d\-]+\b', re.IGNORECASE
)
AMOUNT_RE = re.compile(
    r'(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d{1,2})?)', re.IGNORECASE
)
DATE_RE = re.compile(
    r'\b(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4})\b'
)


def _extract_vendor(doc: Doc, text: str) -> Dict[str, Any]:
    """Try spaCy ORG entity first, fall back to known vendor list."""
    for ent in doc.ents:
        if ent.label_ == 'ORG':
            return {'value': ent.text.strip(), 'confidence': 'HIGH'}
    # Fallback: check if any known vendor name appears in the raw text
    for vendor in KNOWN_VENDORS:
        if vendor.lower() in text.lower():
            return {'value': vendor, 'confidence': 'MEDIUM'}
    return {'value': None, 'confidence': 'LOW'}


def _extract_amount(doc, text: str) -> dict:
    """Try regex with currency symbol first (more reliable than spaCy for Indian amounts)."""
    match = AMOUNT_RE.search(text)
    if match:
        raw = match.group(1).replace(',', '')
        return {'value': raw, 'confidence': 'HIGH'}
    # Fallback: spaCy MONEY entity
    for ent in doc.ents:
        if ent.label_ == 'MONEY':
            return {'value': ent.text, 'confidence': 'MEDIUM'}
    return {'value': None, 'confidence': 'LOW'}


def _extract_date(doc, text: str) -> dict:
    """Regex is more reliable than spaCy for structured date formats."""
    match = DATE_RE.search(text)
    if match:
        return {'value': match.group(), 'confidence': 'HIGH'}
    for ent in doc.ents:
        if ent.label_ == 'DATE':
            return {'value': ent.text, 'confidence': 'MEDIUM'}
    return {'value': None, 'confidence': 'LOW'}


def _extract_invoice_number(text: str) -> dict:
    """Extract invoice number — prefer structured IDs over generic words like 'Invoice'."""
    
    matches = INVOICE_NUM_RE.finditer(text)

    for match in matches:
        value = match.group()

        # ✅ Only accept if it contains at least one digit (real invoice ID)
        if re.search(r'\d', value):
            return {'value': value, 'confidence': 'MEDIUM'}

    return {'value': None, 'confidence': 'LOW'}


def classify_invoice_category(text: str) -> Literal['GOODS', 'SERVICES', 'UNKNOWN']:
    """
    Rule-based classifier: GOODS vs SERVICES.
    In production: replace with a trained text classifier.
    Simple but explainable — exactly what a junior engineer should build first.
    """
    goods_keywords    = ['steel', 'equipment', 'machinery', 'materials', 'parts', 'units']
    services_keywords = ['consulting', 'software', 'maintenance', 'support', 'services', 'license']
    text_lower = text.lower()
    goods_score    = sum(1 for k in goods_keywords    if k in text_lower)
    services_score = sum(1 for k in services_keywords if k in text_lower)
    if goods_score == services_score == 0:
        return 'UNKNOWN'
    return 'GOODS' if goods_score >= services_score else 'SERVICES'


def parse_invoice_text(text: str) -> Dict[str, Any]:
    """
    Main entry point for invoice parsing.
    Runs the spaCy pipeline once, then calls each extractor.
    Extractors are separate functions — easy to test and replace independently.
    """
    doc = nlp(text)   # run full NLP pipeline once

    vendor         = _extract_vendor(doc, text)
    amount         = _extract_amount(doc, text)
    due_date       = _extract_date(doc, text)
    invoice_number = _extract_invoice_number(text)
    category       = classify_invoice_category(text)

    fields = [vendor, amount, due_date, invoice_number]
    requires_review = any(f['confidence'] == 'LOW' for f in fields)

    return {
        'vendor':         vendor,
        'amount':         amount,
        'due_date':       due_date,
        'invoice_number': invoice_number,
        'category':       category,
        'requires_review': requires_review,
    }


def parse_invoices_batch(texts: List[str]) -> List[Dict[str, Any]]:
    """
    Batch parsing using spaCy's pipe() — processes multiple texts efficiently.
    nlp.pipe() is significantly faster than calling nlp() in a loop
    because it batches tokenisation and model inference.
    Use this in a Celery task for high-volume processing.
    """
    results = []
    for doc, text in zip(nlp.pipe(texts, batch_size=16), texts):
        vendor         = _extract_vendor(doc, text)
        amount         = _extract_amount(doc, text)
        due_date       = _extract_date(doc, text)
        invoice_number = _extract_invoice_number(text)
        category       = classify_invoice_category(text)
        fields = [vendor, amount, due_date, invoice_number]
        results.append({
            'vendor': vendor, 'amount': amount,
            'due_date': due_date, 'invoice_number': invoice_number,
            'category': category,
            'requires_review': any(f['confidence'] == 'LOW' for f in fields),
        })
    return results


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extract all text from a PDF file given its raw bytes.
    Returns concatenated text from all pages.
    Used before parse_invoice_text() when the input is a PDF upload.
    """
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return '\n'.join(text_parts)


def run_three_way_match(invoice: "Invoice") -> str:
    try:
        with transaction.atomic():
            po = invoice.purchase_order

            logger.info(
                "Starting 3-way match for invoice %s (PO: %s)",
                invoice.id, po.id
            )

           # Validate: a GRN must exist before an invoice can be matched
            if not po.grns.exists():
                logger.warning(
                    "3-way match FAILED for invoice %s: No GRN found for PO %s",
                    invoice.id, po.id
                )
                raise ValidationError(
                    "Cannot match invoice: no Goods Receipt Note exists for this PO."
                )

            grn = po.grns.latest('received_at')

            po_amount  = po.total_amount
            grn_amount = grn.received_amount
            inv_amount = invoice.amount

            # Optional but strong improvement 👇
            logger.debug(
                "Amounts → PO: %s, GRN: %s, INV: %s",
                po_amount, grn_amount, inv_amount
            )

            tolerance = po_amount * Decimal('0.05')

            po_inv_match = abs(inv_amount - po_amount) <= tolerance
            po_grn_match = abs(grn_amount - po_amount) <= tolerance

            if po_inv_match and po_grn_match:
                invoice.match_status = Invoice.MatchStatus.MATCHED

                logger.info(
                    "3-way match SUCCESS for invoice %s | PO: %s | Amount: %s",
                    invoice.id, po.id, inv_amount
                )
            else:
                invoice.match_status = Invoice.MatchStatus.DISCREPANCY

                logger.warning(
                    "3-way match DISCREPANCY for invoice %s | PO: %s | "
                    "PO: %s, GRN: %s, INV: %s",
                    invoice.id, po.id,
                    po_amount, grn_amount, inv_amount
                )

            invoice.save(update_fields=['match_status'])

            # If matched, auto-close the PO
            if invoice.match_status == Invoice.MatchStatus.MATCHED:
                po.status = PurchaseOrder.Status.CLOSED
                po.save(update_fields=['status', 'updated_at'])

                logger.info("PO %s CLOSED after successful match", po.id)

            return invoice.match_status

    except ValidationError:
        # Expected business case → do not log as error
        raise

    except Exception as e:
    # Unexpected system failure → MUST log
        logger.error(
            "Critical failure in 3-way match for invoice %s",
            invoice.id,
            exc_info=True
        )
        raise

def get_overdue_invoices(queryset: Optional[QuerySet] = None) -> QuerySet:
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