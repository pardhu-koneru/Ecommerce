from rest_framework import serializers
from .models import Review, ReviewEmbedding
from products.models import Product
from users.models import User


class ReviewListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for review list view.
    Shows basic review info without nested objects.
    """
    user_email = serializers.CharField(source='user.email', read_only=True)
    product_title = serializers.CharField(source='product.title', read_only=True)
    
    class Meta:
        model = Review
        fields = [
            'id', 'rating', 'title', 'text', 'user_email', 'product_title',
            'helpful_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'helpful_count']


class ReviewDetailSerializer(serializers.ModelSerializer):
    """
    Full review detail with user information.
    """
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    product_id = serializers.CharField(source='product.id', read_only=True)
    product_title = serializers.CharField(source='product.title', read_only=True)
    
    class Meta:
        model = Review
        fields = [
            'id', 'product_id', 'product_title', 'rating', 'title', 'text',
            'user_email', 'user_name', 'helpful_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'helpful_count']
    
    def get_user_name(self, obj):
        """Get user's full name or email as fallback."""
        if obj.user.first_name or obj.user.last_name:
            return f"{obj.user.first_name} {obj.user.last_name}".strip()
        return obj.user.email


class ReviewCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new reviews.
    Validates that user hasn't already reviewed this product.
    """
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True),
        write_only=True,
        source='product'
    )
    
    class Meta:
        model = Review
        fields = ['product_id', 'rating', 'title', 'text']
    
    def create(self, validated_data):
        """
        Create review and trigger async embedding regeneration if needed.
        """
        # Get user from request context
        user = self.context['request'].user
        validated_data['user'] = user
        
        review = Review.objects.create(**validated_data)
        return review
    
    def validate(self, data):
        """
        Validate that:
        1. Product exists
        2. User hasn't already reviewed this product
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("User must be authenticated to create a review.")
        
        user = request.user
        product = data.get('product')
        
        # Check for duplicate review (one review per user per product)
        if Review.objects.filter(product=product, user=user).exists():
            raise serializers.ValidationError(
                "You have already reviewed this product. You can only have one review per product."
            )
        
        return data


class ReviewEmbeddingSerializer(serializers.ModelSerializer):
    """
    Serializer for review embeddings with metadata.
    Includes summary information and review statistics.
    """
    product_id = serializers.CharField(source='product.id', read_only=True)
    product_title = serializers.CharField(source='product.title', read_only=True)
    
    class Meta:
        model = ReviewEmbedding
        fields = [
            'id', 'product_id', 'product_title', 'summary', 'review_count',
            'avg_rating', 'is_outdated', 'metadata_json', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'summary', 'embedding', 'is_outdated', 'created_at', 'updated_at'
        ]


class ProductReviewStatsSerializer(serializers.Serializer):
    """
    Serializer for product review statistics.
    Provides aggregated review data for a product.
    """
    total_reviews = serializers.IntegerField()
    avg_rating = serializers.FloatField()
    rating_distribution = serializers.DictField()  # e.g., {"5": 100, "4": 50, ...}
    recent_reviews = ReviewListSerializer(many=True)
    review_summary = serializers.DictField(allow_null=True)  # From ReviewEmbedding metadata
