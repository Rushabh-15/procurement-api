from rest_framework import serializers
from .models import Supplier, PurchaseOrder, LineItem, GoodsReceiptNote, Invoice


class SupplierSerializer(serializers.ModelSerializer):
    """
    ModelSerializer auto-generates fields from the Supplier model.
    fields = '__all__' includes everything.
    read_only_fields prevents those fields from being written via the API.
    """
    class Meta:
        model = Supplier
        fields = ['id', 'name', 'email', 'gst_number', 'is_verified', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_email(self, value):
        """Field-level validation. Runs automatically when serializer.is_valid() is called."""
        if '@' not in value:
            raise serializers.ValidationError("Enter a valid email address.")
        return value.lower()  # normalise to lowercase

    def validate(self, data):
        """Object-level validation. Runs after all field-level validators pass."""
        if data.get('name') and len(data['name']) < 2:
            raise serializers.ValidationError({'name': 'Name must be at least 2 characters.'})
        return data


class LineItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.ReadOnlyField()  # exposes the @property from the model

    class Meta:
        model = LineItem
        fields = ['id', 'description', 'quantity', 'unit_price', 'subtotal']


class PurchaseOrderSerializer(serializers.ModelSerializer):
    """
    Nested serializer: line_items is a reverse relation (related_name='line_items').
    many=True means it's a list. read_only=True means it's output-only.
    """
    line_items = LineItemSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'supplier', 'supplier_name', 'status',
            'total_amount', 'notes', 'created_at', 'line_items'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'supplier_name']

    def validate_total_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Total amount must be greater than zero.")
        return value
    
class GoodsReceiptNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoodsReceiptNote
        fields = ['id', 'purchase_order', 'received_amount', 'received_at', 'notes']
        read_only_fields = ['id', 'received_at']

    def validate_received_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Received amount must be greater than zero.")
        return value


class InvoiceSerializer(serializers.ModelSerializer):
    is_overdue   = serializers.ReadOnlyField()   # exposes the @property
    supplier_name = serializers.CharField(
        source='purchase_order.supplier.name', read_only=True
    )

    class Meta:
        model = Invoice
        fields = [
            'id', 'purchase_order', 'supplier_name', 'invoice_number',
            'amount', 'due_date', 'match_status', 'is_overdue', 'created_at'
        ]
        read_only_fields = ['id', 'match_status', 'is_overdue', 'created_at', 'supplier_name']

    def validate(self, data):
        po = data.get('purchase_order')
        if po and po.status == PurchaseOrder.Status.DRAFT:
            raise serializers.ValidationError(
                {'purchase_order': 'Cannot raise invoice against a DRAFT purchase order.'}
            )
        return data