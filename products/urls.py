from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import ProductViewSet

router = DefaultRouter()
router.register('products', ProductViewSet, basename='products')

urlpatterns = [] + router.urls
