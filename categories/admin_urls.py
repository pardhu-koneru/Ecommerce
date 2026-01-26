from rest_framework.routers import DefaultRouter
from django.urls import path
from .admin_views import AdminCategoryManagementViewSet

router = DefaultRouter()
router.register('admin/categories', AdminCategoryManagementViewSet, basename='admin-categories')

urlpatterns = [] + router.urls
