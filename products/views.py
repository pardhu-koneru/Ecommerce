from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.openapi import OpenApiTypes
import base64
import logging

from .models import Product, ProductImage
from .serializers import (
    ProductSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductAttributeSerializer,
    AgenticRAGQuerySerializer,
    AgenticRAGResponseSerializer,
)
from .services import ProductService

logger = logging.getLogger(__name__)


def _extract_product_ids_from_tool_outputs(tool_outputs):
    """
    Extract unique product IDs from all tool outputs returned by the RAG pipeline.

    Different tools store product IDs under different keys:
      - SQLFilterTool / ComparisonTool / StockCheckTool → products[].id
      - ProductEmbeddingSearchTool / HybridSearchFusionTool / BM25KeywordSearchTool / ImageEmbeddingSearchTool → results[].source_id
      - ReviewEmbeddingSearchTool → results[].product_id
    """
    product_ids = []
    seen = set()

    for entry in tool_outputs:
        result = entry.get("result", entry)

        # Tools that return products[].id
        for product in result.get("products", []):
            pid = product.get("id")
            if pid and pid not in seen:
                seen.add(pid)
                product_ids.append(pid)

        # Tools that return results[].source_id or results[].product_id
        for item in result.get("results", []):
            pid = item.get("source_id") or item.get("product_id")
            if pid and pid not in seen:
                seen.add(pid)
                product_ids.append(pid)

    return product_ids


def _build_product_cards(product_ids, limit=10):
    """
    Given a list of product IDs (strings), return lightweight product card dicts
    with id, title, price, currency, rating_avg, and primary image URL.
    Preserves the ordering from product_ids.
    """
    if not product_ids:
        return []

    products = (
        Product.objects
        .filter(id__in=product_ids[:limit], is_active=True)
        .prefetch_related("images")
    )
    product_map = {}
    for p in products:
        primary = p.images.filter(is_primary=True).first()
        image_url = primary.image.url if primary else None
        product_map[str(p.id)] = {
            "id": str(p.id),
            "title": p.title,
            "price": float(p.price),
            "currency": p.currency,
            "rating_avg": p.rating_avg,
            "primary_image": image_url,
        }

    # Preserve original tool-output ordering
    return [product_map[pid] for pid in product_ids[:limit] if pid in product_map]


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

# ────────────────────────────────────────────────────────────────
# Agentic RAG API Endpoint
# ────────────────────────────────────────────────────────────────

class AgenticRAGQueryView(APIView):
    """
    API endpoint for the Agentic RAG system.
    
    Accepts natural language queries about products and returns:
    - Grounded answer (no hallucinations)
    - Confidence score
    - Query intent + execution plan
    - Tools invoked
    
    Supports multimodal search (text + optional image).
    """
    permission_classes = [AllowAny]

    @extend_schema(
        request=AgenticRAGQuerySerializer,
        responses=AgenticRAGResponseSerializer,
        description="Query the Agentic RAG system for products, comparisons, recommendations, etc.",
        examples=[
            OpenApiExample(
                name="Product Search Example",
                description="Search for gaming laptops under a budget",
                value={
                    "query": "best gaming laptop under 80000",
                },
                request_only=True,
            ),
            OpenApiExample(
                name="Product Search Response",
                description="Example RAG response",
                value={
                    "answer": "Based on available products...",
                    "confidence": 0.92,
                    "intent": "product_search",
                    "plan": ["Run ProductEmbeddingSearchTool...", "Rank final candidates"],
                    "tools_used": ["ProductEmbeddingSearchTool"],
                    "loop_count": 0,
                    "evaluation_notes": "High confidence; grounded answer."
                },
                response_only=True,
            ),
        ]
    )
    def post(self, request, *args, **kwargs):
        """Execute an agentic RAG query."""
        serializer = AgenticRAGQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        query = serializer.validated_data["query"]
        image_file = serializer.validated_data.get("image")

        # Convert image to base64 if provided
        image_b64 = None
        if image_file:
            try:
                image_data = image_file.read()
                image_b64 = base64.standard_b64encode(image_data).decode("utf-8")
            except Exception as e:
                logger.error(f"Failed to encode image: {e}")
                return Response(
                    {"error": "Failed to process image"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Execute agentic RAG query
        try:
            from ai_agentic_rag.graph.workflow import run_query

            result = run_query(query=query, image_data=image_b64)

            # Extract referenced product IDs from tool outputs and build cards
            tool_outputs = result.get("tool_outputs", [])
            product_cards = _build_product_cards(
                _extract_product_ids_from_tool_outputs(tool_outputs)
            )

            response_data = {
                "answer": result.get("answer", ""),
                "confidence": result.get("confidence", 0.0),
                "intent": result.get("intent", ""),
                "plan": result.get("plan", []),
                "tools_used": result.get("tools_used", []),
                "loop_count": result.get("loop_count", 0),
                "evaluation_notes": result.get("evaluation_notes", ""),
                "products": product_cards,
            }

            response_serializer = AgenticRAGResponseSerializer(response_data)
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except ImportError as e:
            logger.error(f"RAG system not available: {e}")
            return Response(
                {"error": "RAG system not initialized"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as e:
            logger.exception(f"RAG query failed: {e}")
            return Response(
                {"error": f"Query processing failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )