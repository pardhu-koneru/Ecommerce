from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.openapi import OpenApiTypes

from .models import Product
from .serializers import (
    ProductSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductAttributeSerializer
)
from .services import ProductService


class ProductViewSet(ReadOnlyModelViewSet):
    """
    Read-only endpoints for users to view products.
    Supports filtering, searching, and detailed product views.
    """
    queryset = Product.objects.filter(is_active=True).prefetch_related('attributes', 'images')
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        elif self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductSerializer

    @extend_schema(
        description="List all active products with filtering and search",
        parameters=[
            OpenApiParameter(
                name='category',
                description='Filter by category slug (e.g., electronics)',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='price_min',
                description='Minimum price filter',
                required=False,
                type=OpenApiTypes.DECIMAL
            ),
            OpenApiParameter(
                name='price_max',
                description='Maximum price filter',
                required=False,
                type=OpenApiTypes.DECIMAL
            ),
            OpenApiParameter(
                name='brand',
                description='Filter by brand name',
                required=False,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='in_stock',
                description='Filter by stock availability (true/false)',
                required=False,
                type=OpenApiTypes.BOOL
            ),
            OpenApiParameter(
                name='rating_min',
                description='Minimum rating filter (0-5)',
                required=False,
                type=OpenApiTypes.DECIMAL
            ),
            OpenApiParameter(
                name='search',
                description='Search in title, description, or brand (case-insensitive)',
                required=False,
                type=OpenApiTypes.STR
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        """
        Get all active products with optional filters:
        - category: Category slug
        - price_min / price_max: Price range
        - brand: Brand name
        - in_stock: True/False
        - rating_min: Minimum rating (0-5)
        - search: Search in title/description
        
        Example: /api/products/?category=electronics&price_min=100&price_max=1000&search=iphone
        """
        queryset = self.get_queryset()
        
        # Apply filters from query parameters
        filters = {
            'category': request.query_params.get('category'),
            'price_min': request.query_params.get('price_min'),
            'price_max': request.query_params.get('price_max'),
            'brand': request.query_params.get('brand'),
            'in_stock': request.query_params.get('in_stock'),
            'rating_min': request.query_params.get('rating_min'),
            'search': request.query_params.get('search'),
        }
        
        # Remove None values
        filters = {k: v for k, v in filters.items() if v is not None}
        
        # Apply service filtering
        queryset = ProductService.filter_products(queryset, filters)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(description="Get detailed product information with specs and images")
    def retrieve(self, request, *args, **kwargs):
        """Get detailed product information with all attributes and images"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        description="Get products in a specific category",
        parameters=[
            OpenApiParameter(
                name='slug',
                description='Category slug (required)',
                required=True,
                type=OpenApiTypes.STR
            ),
        ]
    )
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def by_category(self, request):
        """Get products filtered by category"""
        category_slug = request.query_params.get('slug')
        if not category_slug:
            return Response(
                {'detail': 'category slug parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(category__slug=category_slug)
        serializer = ProductListSerializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
        description="Search products by title, description, or brand",
        parameters=[
            OpenApiParameter(
                name='q',
                description='Search query (minimum 2 characters)',
                required=True,
                type=OpenApiTypes.STR
            ),
        ]
    )
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def search(self, request):
        """Search products"""
        search_term = request.query_params.get('q')
        if not search_term or len(search_term) < 2:
            return Response(
                {'detail': 'Search term must be at least 2 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(
            title__icontains=search_term
        ) | self.get_queryset().filter(
            description__icontains=search_term
        ) | self.get_queryset().filter(
            brand__icontains=search_term
        )
        
        serializer = ProductListSerializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(description="Get featured products (highest rated)")
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def featured(self, request):
        """Get featured products (top rated, in stock)"""
        queryset = self.get_queryset().filter(
            rating_avg__gte=4.0,
            stock_quantity__gt=0
        ).order_by('-rating_avg')[:10]
        
        serializer = ProductListSerializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(description="Get new arrivals")
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def new_arrivals(self, request):
        """Get recently added products"""
        queryset = self.get_queryset().order_by('-created_at')[:10]
        serializer = ProductListSerializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
        description="Get product recommendations based on rating",
        parameters=[
            OpenApiParameter(
                name='limit',
                description='Maximum number of recommendations (default: 10)',
                required=False,
                type=OpenApiTypes.INT
            ),
        ]
    )
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def recommendations(self, request):
        """Get product recommendations"""
        limit = int(request.query_params.get('limit', 10))
        queryset = self.get_queryset().filter(
            rating_count__gt=10  # Only products with enough reviews
        ).order_by('-rating_avg')[:limit]
        
        serializer = ProductListSerializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(description="Get product attributes (specs, features, etc.)")
    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def attributes(self, request,id=None):
        """
        Get all attributes (specs, features) for a specific product.
        
        Database Retrieval:
        - Uses prefetch_related to avoid N+1 queries
        - Single query to fetch product
        - Single query to fetch related attributes
        
        Example: /api/products/{product_id}/attributes/
        """
        try:
            product = self.get_queryset().get(id=id)
            
            # Attributes already prefetched via queryset.prefetch_related('attributes')
            attributes = product.attributes.all()
            serializer = ProductAttributeSerializer(attributes, many=True)
            
            return Response({
                'product_id': str(product.id),
                'product_title': product.title,
                'attributes': serializer.data
            })
        except Product.DoesNotExist:
            return Response(
                {'detail': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
