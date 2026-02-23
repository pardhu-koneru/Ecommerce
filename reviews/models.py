from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from products.models import Product
from users.models import User
import uuid
from django.utils import timezone
import json

try:
    from pgvector.django import VectorField
except ImportError:
    VectorField = models.BinaryField  # Fallback


class Review(models.Model):
    """
    User review model for products.
    Stores rating and text-based reviews from customers.
    
    Metadata tied to this review:
    - Product being reviewed
    - User who wrote the review
    - Rating (1-5 stars)
    - Review text
    - Timestamps for tracking
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Rating from 1 to 5 stars"
    )
    title = models.CharField(max_length=200, blank=True)
    text = models.TextField(help_text="User's review text")
    
    # Metadata
    helpful_count = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reviews_review'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product', '-created_at']),
            models.Index(fields=['user']),
            models.Index(fields=['rating']),
            models.Index(fields=['created_at']),
        ]
        # One review per user per product (prevent duplicates)
        unique_together = ['product', 'user']

    def __str__(self):
        return f"Review by {self.user.email} for {self.product.title} - {self.rating}★"


class ReviewEmbedding(models.Model):
    """
    AI-generated summary and embeddings for product reviews.
    
    This table stores:
    - Aggregated summary of all reviews for a product
    - Vector embedding of that summary
    - Metadata about the reviews (count, avg rating, sentiment, etc.)
    
    REGENERATION STRATEGY:
    - Triggered every 5 new reviews
    - Stores metadata about when it was last updated
    - Includes sentiment analysis and review statistics
    
    Example metadata:
    {
      "type": "review_summary",
      "review_count": 124,
      "avg_rating": 4.3,
      "sentiment": "mostly_positive",
      "last_updated_at": "2026-02-22T10:30:00",
      "product_title": "iPhone 15",
      "category": "Electronics",
      "min_rating": 1,
      "max_rating": 5,
      "reviews_since_last_embed": 3
    }
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='review_embedding')
    
    # Summary text generated from all reviews
    summary = models.TextField(help_text="AI-generated summary of all product reviews")
    
    # Vector embedding of the summary (768-dim for nomic-embed-text)
    embedding = VectorField(dimensions=768, null=True, blank=True)
    
    # Metadata about reviews and embeddings
    metadata_json = models.JSONField(default=dict)
    
    # Tracking for batch regeneration
    review_count = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    avg_rating = models.FloatField(default=0.0, validators=[MinValueValidator(0), MaxValueValidator(5)])
    
    # When was this generated?
    is_outdated = models.BooleanField(default=False, help_text="True if 5+ new reviews since last update")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reviews_review_embedding'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['product']),
            models.Index(fields=['is_outdated']),
            models.Index(fields=['updated_at']),
        ]

    def __str__(self):
        return f"ReviewEmbedding for {self.product.title} ({self.review_count} reviews)"
