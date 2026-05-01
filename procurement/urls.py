from rest_framework.routers import DefaultRouter
from django.urls import path, include
from . import views

router = DefaultRouter()
router.register(r'suppliers', views.SupplierViewSet, basename='supplier')
router.register(r'purchase-orders', views.PurchaseOrderViewSet, basename='purchase-order')
router.register(r'grns', views.GoodsReceiptNoteViewSet, basename='grn')
router.register(r'invoices', views.InvoiceViewSet, basename='invoice')

urlpatterns = [
    path('invoices/parse/', views.InvoiceParseView.as_view(), name='invoice-parse'),
    path('', include(router.urls)),
]
# Router auto-generates ALL these patterns:
# GET/POST  /api/suppliers/
# GET/PUT/PATCH/DELETE  /api/suppliers/{id}/
# GET/POST  /api/purchase-orders/
# GET/PUT/PATCH/DELETE  /api/purchase-orders/{id}/
# POST      /api/purchase-orders/{id}/approve/   ← custom action