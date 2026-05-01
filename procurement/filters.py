import django_filters
from .models import PurchaseOrder


class PurchaseOrderFilter(django_filters.FilterSet):
    """
    Custom filter class gives you range filters, lookups, and multi-value filters.
    This cannot be done with filterset_fields alone.
    """
    min_amount = django_filters.NumberFilter(field_name='total_amount', lookup_expr='gte')
    max_amount = django_filters.NumberFilter(field_name='total_amount', lookup_expr='lte')
    created_after  = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_before = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    supplier_name  = django_filters.CharFilter(field_name='supplier__name', lookup_expr='icontains')

    class Meta:
        model = PurchaseOrder
        fields = ['status', 'supplier']