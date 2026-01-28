from rest_framework.routers import DefaultRouter
from django.urls import path
from .admin_views import AdminProductManagementViewSet

router = DefaultRouter()
router.register('admin/products', AdminProductManagementViewSet, basename='admin-products')

urlpatterns = [] + router.urls
