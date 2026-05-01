from django.db import models
from django.contrib.auth.models import AbstractUser
# Create your models here.
    
class User(AbstractUser):
    def __str__(self):
        return self.username


class Supplier(models.Model):
    """A vendor that supplies goods or services to a company."""
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    gst_number = models.CharField(max_length=20, blank=True)
    is_verified = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_suppliers'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']  # newest first by default

    def __str__(self):
        return f"{self.name} ({self.email})"


class PurchaseOrder(models.Model):
    """A formal order raised to a supplier for goods/services."""

    class Status(models.TextChoices):
        # TextChoices gives you DRAFT, APPROVED, CLOSED as string constants
        # AND a human-readable label — Django validates these in forms/serializers
        DRAFT    = 'DRAFT',    'Draft'
        APPROVED = 'APPROVED', 'Approved'
        CLOSED   = 'CLOSED',   'Closed'

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,  # PROTECT: can't delete a supplier that has POs
        related_name='purchase_orders'
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
        # DecimalField for money — NEVER use FloatField (float arithmetic is imprecise)
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"PO-{self.pk} | {self.supplier.name} | {self.status}"


class LineItem(models.Model):
    """One line in a purchase order — a specific item or service."""
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,  # CASCADE: deleting a PO also deletes its line items
        related_name='line_items'
    )
    description = models.CharField(max_length=500)
    quantity     = models.PositiveIntegerField()
    unit_price   = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def subtotal(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.description} x {self.quantity} (PO-{self.purchase_order_id})"
    
class GoodsReceiptNote(models.Model):
    """
    Confirms that goods/services were physically received.
    This is the second leg of the 3-way match:
    PurchaseOrder (ordered) + GRN (received) + Invoice (billed).
    """
    purchase_order  = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name='grns'
    )
    received_by     = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='grns_received'
    )
    received_amount = models.DecimalField(max_digits=12, decimal_places=2)
    received_at     = models.DateTimeField(auto_now_add=True)
    notes           = models.TextField(blank=True)

    def __str__(self):
        return f"GRN for PO-{self.purchase_order_id} | ₹{self.received_amount}"


class Invoice(models.Model):
    class MatchStatus(models.TextChoices):
        PENDING     = 'PENDING',     'Pending'
        MATCHED     = 'MATCHED',     'Matched'
        DISCREPANCY = 'DISCREPANCY', 'Discrepancy'

    purchase_order  = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name='invoices'
    )
    invoice_number  = models.CharField(max_length=100, unique=True)
    amount          = models.DecimalField(max_digits=12, decimal_places=2)
    due_date        = models.DateField()
    match_status    = models.CharField(
        max_length=20, choices=MatchStatus.choices, default=MatchStatus.PENDING
    )
    raw_text        = models.TextField(blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice {self.invoice_number} | ₹{self.amount} | {self.match_status}"

    @property
    def is_overdue(self):
        from django.utils import timezone
        return self.due_date < timezone.now().date() and self.match_status != Invoice.MatchStatus.MATCHED