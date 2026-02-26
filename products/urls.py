from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import ProductViewSet, AgenticRAGQueryView

router = DefaultRouter()
router.register('products', ProductViewSet, basename='products')

urlpatterns = [
    path('rag-query/', AgenticRAGQueryView.as_view(), name='rag-query'),
] + router.urls
