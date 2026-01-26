from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema

from .models import Category
from .serializers import (
    CategorySerializer,
    CategoryListSerializer
)
from .services import CategoryService


class CategoryViewSet(ReadOnlyModelViewSet):
    """
    Read-only endpoints for users to view categories.
    """
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'list':
            return CategoryListSerializer
        return CategorySerializer

    @extend_schema(description="List all active categories with hierarchical structure")
    def list(self, request, *args, **kwargs):
        """Get all active categories, optionally filtered"""
        queryset = self.get_queryset()
        
        # Only show root categories in list view
        if request.query_params.get('root_only'):
            queryset = queryset.filter(parent__isnull=True)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(description="Get a specific category by slug")
    def retrieve(self, request, *args, **kwargs):
        """Get category details by slug"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(description="Get subcategories of a parent category")
    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def subcategories(self, request, slug=None):
        """Get all subcategories of a category"""
        try:
            category = Category.objects.get(slug=slug)
            subcategories = category.children.filter(is_active=True)
            serializer = CategoryListSerializer(subcategories, many=True)
            return Response(serializer.data)
        except Category.DoesNotExist:
            return Response(
                {'detail': 'Category not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @extend_schema(description="Get category count statistics")
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def stats(self, request):
        """Get category statistics"""
        stats = CategoryService.get_stats()
        return Response(stats)
