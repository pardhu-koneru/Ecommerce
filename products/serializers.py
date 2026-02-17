from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Product, ProductAttribute, ProductImage, AIDocument


class ProductAttributeSerializer(serializers.ModelSerializer):
    """Serializer for product attributes (key-value pairs)"""
    class Meta:
        model = ProductAttribute
        fields = ['id', 'key', 'value']


class ProductImageSerializer(serializers.ModelSerializer):
    """Serializer for product images"""
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_primary', 'display_order']
        read_only_fields = ['id']


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for product list view"""
    primary_image = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = ['id', 'title', 'price', 'currency', 'rating_avg', 'rating_count', 'is_active', 'primary_image']
        read_only_fields = ['id']
    
    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_primary_image(self, obj) -> dict | None:
        """Get the primary image URL"""
        primary = obj.images.filter(is_primary=True).first()
        if primary:
            return ProductImageSerializer(primary).data
        return None


class ProductDetailSerializer(serializers.ModelSerializer):
    """Full product details with attributes and images"""
    attributes = ProductAttributeSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'title', 'description', 'brand', 'category', 'category_name',
            'price', 'currency', 'stock_quantity', 'is_active', 'rating_avg',
            'rating_count', 'attributes', 'images', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CreateUpdateProductSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating products"""
    attributes = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        write_only=True
    )
    
    class Meta:
        model = Product
        fields = [
            'title', 'description', 'brand', 'category', 'price', 'currency',
            'stock_quantity', 'is_active', 'attributes'
        ]
    
    def validate_category(self, value):
        """Validate that category exists"""
        if not value:
            raise serializers.ValidationError("Category is required")
        return value
    
    def validate_price(self, value):
        """Validate price is positive"""
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0")
        return value
    
    def validate_stock_quantity(self, value):
        """Validate stock quantity is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Stock quantity cannot be negative")
        return value


class ProductSerializer(serializers.ModelSerializer):
    """Default serializer for product responses"""
    attributes = ProductAttributeSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'title', 'description', 'brand', 'category', 'category_name',
            'price', 'currency', 'stock_quantity', 'is_active', 'rating_avg',
            'rating_count', 'attributes', 'images', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AddAttributesSerializer(serializers.Serializer):
    """Serializer for adding attributes to a product"""
    attributes = serializers.DictField(
        child=serializers.CharField(),
        required=True,
        help_text="Dictionary of attribute key-value pairs (e.g., {'ram': '16GB', 'processor': 'i7'})"
    )
    
    def validate_attributes(self, value):
        """Validate attributes dictionary"""
        if not value:
            raise serializers.ValidationError("Attributes dictionary cannot be empty")
        
        if not isinstance(value, dict):
            raise serializers.ValidationError("Attributes must be a dictionary")
        
        for key, val in value.items():
            if not isinstance(key, str) or not key.strip():
                raise serializers.ValidationError("Attribute keys must be non-empty strings")
            if not isinstance(val, str) or not val.strip():
                raise serializers.ValidationError("Attribute values must be non-empty strings")
        
        return value


class UploadProductImageSerializer(serializers.Serializer):
    """Serializer for uploading product images"""
    image = serializers.ImageField(
        required=True,
        help_text="Product image file (PNG, JPG, etc.)"
    )
    alt_text = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Alternative text for the image"
    )
    is_primary = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Set as primary image for product"
    )
