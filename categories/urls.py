from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import CategoryViewSet

router = DefaultRouter()
router.register('categories', CategoryViewSet, basename='categories')

urlpatterns = [] + router.urls
