from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsVerifiedSupplierOrReadOnly(BasePermission):
    """
    Write access (POST, PUT, PATCH, DELETE) is only allowed if the supplier being created/modifed is verified. Read access (GET, HEAD, OPTIONS) is always allowed for authenticated users.

    This teaches two things:
    1. How to write a custom permission class
    2. The SAFE_METHODS tuple: ("GET", "HEAD", "OPTIONS")
    """

    def has_permission(self, request, view):
        # has_permission: runs on EVERY request to this view
        if request.method in SAFE_METHODS:
            return True # allow all GET requests
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        # Only allow editing a verified supplier
        return obj.is_verified
    
class IsOwnerOrReadOnly(BasePermission):
    """
    Only the user who created the PurchaseOrder can modify it.
    This is the pattern for user-owned resources.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.created_by == request.user