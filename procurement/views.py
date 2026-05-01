from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from .services import run_three_way_match, parse_invoice_text, get_overdue_invoices
from .models import Supplier, PurchaseOrder, GoodsReceiptNote, Invoice
from .serializers import (
    SupplierSerializer, PurchaseOrderSerializer,
    GoodsReceiptNoteSerializer, InvoiceSerializer
)
from .permissions import IsOwnerOrReadOnly
from .filters import PurchaseOrderFilter

class SupplierViewSet(viewsets.ModelViewSet):
    """
    ModelViewSet auto-generates all 5 actions:
      list()    → GET  /suppliers/
      create()  → POST /suppliers/
      retrieve()→ GET  /suppliers/{id}/
      update()  → PUT  /suppliers/{id}/
      destroy() → DELETE /suppliers/{id}/
    You get all of these for free. No boilerplate.
    """
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Always override get_queryset — never use queryset = Model.objects.all()
        # This gives you control: tomorrow we'll add tenant filtering here
        return Supplier.objects.select_related('created_by').order_by('-created_at')

    def perform_create(self, serializer):
        # Hook that runs just before save() — inject extra data here
        # e.g. auto-set created_by from the logged-in user
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='verify')
    def verify(self, request, pk=None):
        supplier = self.get_object()

        if supplier.is_verified:
            return Response(
                {'error': 'Supplier is already verified.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        supplier.is_verified = True
        supplier.save(update_fields=['is_verified'])

        return Response({'status': 'verified', 'id': supplier.id})
    
    @action(detail=True, methods=['get'], url_path='purchase-orders')
    def purchase_orders(self, request, pk=None):
        supplier = self.get_object()

        pos = supplier.purchase_orders.select_related(
            'supplier', 'created_by'
        )
        serializer = PurchaseOrderSerializer(pos, many=True)

        return Response(serializer.data)

class PurchaseOrderViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    filterset_class = PurchaseOrderFilter
    search_fields = ['supplier__name', 'notes']
    ordering_fields = ['created_at', 'total_amount']

    def get_queryset(self):
        return PurchaseOrder.objects.select_related(
            'supplier', 'created_by'
        ).prefetch_related(
            'line_items'
        ).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        """
        Custom action — creates endpoint: POST /purchase-orders/{id}/approve/
        detail=True means it operates on a single object (needs pk in URL).
        """
        po = self.get_object()  # fetches PO by pk, runs permission check
        if po.status != PurchaseOrder.Status.DRAFT:
            return Response(
                {'error': 'Only DRAFT orders can be approved.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        po.status = PurchaseOrder.Status.APPROVED
        po.save(update_fields=['status', 'updated_at'])
        return Response({'status': 'approved', 'id': po.id})
    
    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        po = self.get_object()

        if po.status != PurchaseOrder.Status.APPROVED:
            return Response(
                {'error': 'Only APPROVED orders can be closed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        po.status = PurchaseOrder.Status.CLOSED
        po.save(update_fields=['status', 'updated_at'])

        return Response({'status': 'closed', 'id': po.id})
    
class InvoiceParseView(APIView):
    """Standalone view for the invoice parser — not a ModelViewSet."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = request.data.get('text', '')
        if not text.strip():
            return Response(
                {'error': 'text field is required and cannot be empty.'},
                status=status.HTTP_400_BAD_REQUEST
                )
        result = parse_invoice_text(text)
        return Response(result, status=status.HTTP_200_OK)
    
class GoodsReceiptNoteViewSet(viewsets.ModelViewSet):
    serializer_class   = GoodsReceiptNoteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return GoodsReceiptNote.objects.select_related(
            'purchase_order__supplier', 'received_by'
        ).order_by('-received_at')

    def perform_create(self, serializer):
        serializer.save(received_by=self.request.user)


class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class   = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields   = ['match_status', 'purchase_order']
    ordering_fields    = ['due_date', 'amount', 'created_at']

    def get_queryset(self):
        return Invoice.objects.select_related(
            'purchase_order__supplier'
        ).order_by('-created_at')

    def perform_create(self, serializer):
        # Save the invoice first, then immediately run the 3-way match
        invoice = serializer.save()
        try:
            run_three_way_match(invoice)
        except Exception:
            pass   # match stays PENDING if GRN doesn't exist yet — that's valid

    @action(detail=False, methods=['get'], url_path='overdue')
    def overdue(self, request):
        """GET /api/invoices/overdue/ — returns all overdue invoices."""
        qs     = self.get_queryset()
        result = get_overdue_invoices(qs)
        serializer = self.get_serializer(result, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='match')
    def match(self, request, pk=None):
        """POST /api/invoices/{id}/match/ — manually trigger 3-way match."""
        invoice = self.get_object()
        try:
            status_result = run_three_way_match(invoice)
            return Response({'match_status': status_result, 'invoice_id': invoice.id})
        except Exception as e:
            return Response({'error': str(e)}, status=400)