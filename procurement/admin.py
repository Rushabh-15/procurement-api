from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Supplier, PurchaseOrder, LineItem, GoodsReceiptNote, Invoice

# Register your models here.

admin.site.register(User, UserAdmin)
admin.site.register(Supplier)
admin.site.register(PurchaseOrder)
admin.site.register(LineItem)
admin.site.register(GoodsReceiptNote)
admin.site.register(Invoice)