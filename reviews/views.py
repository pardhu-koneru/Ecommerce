from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.openapi import OpenApiTypes
from django.db.models import Avg, Count, Q

from .models import Review, ReviewEmbedding
from .serializers import (
    ReviewListSerializer,
    ReviewDetailSerializer,
    ReviewCreateSerializer,
    ReviewEmbeddingSerializer,
    ProductReviewStatsSerializer
)
from products.models import Product


class ReviewViewSet(viewsets.ModelViewSet):
    """
    Endpoints for managing product reviews.
    
    Supports:
    - Creating new reviews (1-5 rating + text)
    - Listing reviews by product
    - Retrieving review details
    - Filtering reviews by product and rating
    """
    serializer_class = ReviewListSerializer
    permission_classes = [AllowAny]
    lookup_field = 'id'
    
    def get_queryset(self):
        """
        Filter reviews by product if product_id is in query params.
        """
        queryset = Review.objects.select_related('user', 'product')
        
        product_id = self.request.query_params.get('product_id')
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        
        rating = self.request.query_params.get('rating')
        if rating:
            try:
                rating = int(rating)
                if 1 <= rating <= 5:
                    queryset = queryset.filter(rating=rating)
            except (ValueError, TypeError):
                pass
        
        return queryset.order_by('-created_at')
    
    def get_serializer_class(self):
        """Use different serializers based on action."""
        if self.action == 'create':
            return ReviewCreateSerializer
        elif self.action == 'retrieve':
            return ReviewDetailSerializer
        elif self.action == 'list':
            return ReviewListSerializer
        return ReviewListSerializer
    
    def get_permissions(self):
        """
        Allow anyone to view reviews.
        Only authenticated users can create reviews.
        Only review authors can update/delete their reviews.
        """
        if self.action in ['create']:
            permission_classes = [IsAuthenticated]
        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [AllowAny]
        
        return [permission() for permission in permission_classes]
    
    @extend_schema(
        description="Create a new review for a product (1-5 rating)",
        request=ReviewCreateSerializer,
        responses={201: ReviewDetailSerializer}
    )
    def create(self, request, *args, **kwargs):
        """
        Create new review with automatic async embedding regeneration.
        
        Request body:
        {
            "product_id": "uuid",
            "rating": 5,
            "title": "Great laptop!",
            "text": "This laptop is amazing. Works well for gaming..."
        }
        """
        return super().create(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        """
        Save review and trigger async embedding task.
        """
        review = serializer.save()
        
        # Trigger async review embedding regeneration if needed
        from .tasks import check_and_regenerate_review_embedding
        check_and_regenerate_review_embedding.delay(str(review.product_id))
    
    def perform_update(self, serializer):
        """
        Update review and trigger async embedding regeneration.
        """
        review = serializer.save()
        
        from .tasks import check_and_regenerate_review_embedding
        check_and_regenerate_review_embedding.delay(str(review.product_id))
    
    @extend_schema(
        description="Get review statistics and summary for a product"
    )
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def product_stats(self, request):
        """
        Get aggregated review statistics for a product.
        
        Query params:
        - product_id: Required. UUID of the product
        
        Response includes:
        - total_reviews: Total number of reviews
        - avg_rating: Average rating (1-5)
        - rating_distribution: Count by each star level
        - recent_reviews: Last 5 reviews
        - review_summary: AI-generated summary from ReviewEmbedding
        """
        product_id = request.query_params.get('product_id')
        
        if not product_id:
            return Response(
                {"error": "product_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response(
                {"error": "Product not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get all reviews for this product
        reviews = Review.objects.filter(product=product)
        
        # Calculate statistics
        stats = reviews.aggregate(
            total_reviews=Count('id'),
            avg_rating=Avg('rating')
        )
        
        # Get rating distribution
        rating_dist = {}
        for i in range(1, 6):
            rating_dist[str(i)] = reviews.filter(rating=i).count()
        
        # Get recent reviews
        recent_reviews = reviews.order_by('-created_at')[:5]
        
        # Get AI summary from ReviewEmbedding if available
        review_summary = None
        try:
            embedding = ReviewEmbedding.objects.get(product=product)
            review_summary = {
                'summary': embedding.summary,
                'metadata': embedding.metadata_json,
                'is_outdated': embedding.is_outdated,
                'generated_at': embedding.updated_at.isoformat()
            }
        except ReviewEmbedding.DoesNotExist:
            pass
        
        data = {
            'total_reviews': stats['total_reviews'],
            'avg_rating': stats['avg_rating'] or 0.0,
            'rating_distribution': rating_dist,
            'recent_reviews': ReviewListSerializer(recent_reviews, many=True).data,
            'review_summary': review_summary
        }
        
        return Response(data, status=status.HTTP_200_OK)
    
    @extend_schema(
        description="Search reviews by keyword (searches in title and text)",
        parameters=[
            OpenApiParameter(
                name='q',
                description='Search keyword/query',
                required=True,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='product_id',
                description='Filter by product ID',
                required=False,
                type=OpenApiTypes.STR
            ),
        ]
    )
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def search(self, request):
        """
        Search reviews by keyword.
        
        Query params:
        - q: Search term (required)
        - product_id: Filter by product (optional)
        
        Searches in review title and text fields.
        """
        query = request.query_params.get('q', '').strip()
        
        if not query:
            return Response(
                {"error": "Search query 'q' is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        reviews = Review.objects.filter(
            Q(title__icontains=query) | Q(text__icontains=query)
        )
        
        product_id = request.query_params.get('product_id')
        if product_id:
            reviews = reviews.filter(product_id=product_id)
        
        reviews = reviews.order_by('-created_at')
        page = self.paginate_queryset(reviews)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(reviews, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        description="Ask a question about a product using AI-powered review analysis",
        parameters=[
            OpenApiParameter(
                name='q',
                description='Question about the product',
                required=True,
                type=OpenApiTypes.STR
            ),
            OpenApiParameter(
                name='product_id',
                description='Product ID (optional - searches across all products if not specified)',
                required=False,
                type=OpenApiTypes.STR
            ),
        ]
    )
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def ask_question(self, request):
        """
        Ask a question about a product using AI-powered analysis of customer reviews.
        
        This endpoint uses review embeddings and LLM to answer specific questions
        about products based on what customers have actually said.
        
        Query params:
        - q: Required. The question (e.g., "Does this laptop overheat while gaming?")
        - product_id: Optional. Specific product to ask about
        
        Examples:
        - GET /api/reviews/ask_question/?q=Does%20this%20laptop%20overheat
        - GET /api/reviews/ask_question/?q=How%20is%20battery%20life&product_id=<uuid>
        - GET /api/reviews/ask_question/?q=Is%20this%20product%20durable
        
        Response:
        {
            "question": "Does this laptop overheat while gaming?",
            "answer": "According to customer reviews, ...",
            "confidence": "high|medium|low",
            "supporting_reviews": [count of reviews analyzed],
            "products_analyzed": [count of products searched]
        }
        """
        from .services import ReviewRAGService
        
        question = request.query_params.get('q', '').strip()
        product_id = request.query_params.get('product_id', None)
        
        if not question:
            return Response(
                {"error": "Question 'q' is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate product_id if provided
        if product_id:
            try:
                Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                return Response(
                    {"error": "Product not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Get AI-powered answer
        answer = ReviewRAGService.get_ai_answer_to_review_question(question, product_id)
        
        # Get context about how many reviews were analyzed
        relevant_reviews = ReviewRAGService.search_reviews_for_question(question, product_id)
        
        data = {
            'question': question,
            'answer': answer,
            'supporting_reviews': sum(r['review_count'] for r in relevant_reviews),
            'products_analyzed': len(relevant_reviews),
            'confidence': 'high' if len(relevant_reviews) > 2 else 'medium' if len(relevant_reviews) > 0 else 'low'
        }
        
        return Response(data, status=status.HTTP_200_OK)