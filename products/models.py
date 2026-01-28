from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from categories.models import Category
import uuid
import json


class Product(models.Model):
    """
    Core product model.
    This is the source of truth for product data.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField()
    brand = models.CharField(max_length=100, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default='INR')  # ISO 4217 code
    stock_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    
    # Ratings (denormalized from reviews for fast access)
    rating_avg = models.FloatField(default=0.0, validators=[MinValueValidator(0), MaxValueValidator(5)])
    rating_count = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products_product'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['is_active']),
            models.Index(fields=['price']),
            models.Index(fields=['rating_avg']),
            models.Index(fields=['created_at']),
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return self.title


class ProductAttribute(models.Model):
    """
    Entity-Attribute-Value (EAV) pattern for flexible product attributes.
    
    Examples:
    - key: "color", value: "red"
    - key: "size", value: "L"
    - key: "processor", value: "Intel i9"
    - key: "ram", value: "16GB"
    
    This allows products to have different attributes without rigid schema.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='attributes')
    key = models.CharField(max_length=100)  # e.g., "color", "size", "processor"
    value = models.TextField()  # e.g., "red", "L", "Intel i9"

    class Meta:
        db_table = 'products_product_attribute'
        unique_together = ['product', 'key']  # One value per key per product
        indexes = [
            models.Index(fields=['product']),
            models.Index(fields=['key']),
        ]

    def __str__(self):
        return f"{self.product.title} - {self.key}: {self.value}"


class ProductImage(models.Model):
    """
    Product images with primary image designation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/%Y/%m/')
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'products_product_image'
        ordering = ['display_order', 'created_at']
        indexes = [
            models.Index(fields=['product', 'is_primary']),
            models.Index(fields=['product']),
        ]

    def __str__(self):
        return f"{self.product.title} - Image"

    def save(self, *args, **kwargs):
        """
        Ensure only one primary image per product.
        """
        if self.is_primary:
            # Remove primary flag from other images
            ProductImage.objects.filter(product=self.product, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class AIDocument(models.Model):
    """
    AI-readable document layer.
    
    This is the ONLY thing LLMs should read.
    NOT the raw Product table.
    
    Stores curated text content for RAG (Retrieval Augmented Generation).
    
    Flow:
    1. Product changes → Trigger regeneration
    2. Convert to text_content (via service)
    3. Store metadata (for traceability)
    4. Async task generates embeddings
    5. LLM receives this document + embeddings
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Traceability: where did this document come from?
    source_type = models.CharField(
        max_length=50,
        choices=[
            ('product', 'Product'),
            ('review', 'Review'),
            ('category', 'Category'),
        ]
    )
    source_id = models.CharField(max_length=255)  # UUID of the source
    
    # The actual content LLM reads
    text_content = models.TextField()
    
    # Metadata for filtering/tracing back
    metadata_json = models.JSONField(default=dict)
    # Example metadata:
    # {
    #   "product_title": "iPhone 15",
    #   "category": "Electronics",
    #   "price": 999,
    #   "version": 1,
    #   "generated_by": "ProductDocumentService"
    # }
    
    # Status tracking
    is_indexed = models.BooleanField(default=False)  # Has embedding been created?
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products_ai_document'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['source_type', 'source_id']),
            models.Index(fields=['is_indexed']),
            models.Index(fields=['created_at']),
        ]
        # Ensure one document per source
        unique_together = ['source_type', 'source_id']

    def __str__(self):
        return f"AIDocument({self.source_type}:{self.source_id})"

