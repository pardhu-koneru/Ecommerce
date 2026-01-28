from django.db import transaction
from django.core.exceptions import ValidationError
from categories.models import Category
from .models import Product, ProductAttribute, ProductImage, AIDocument


class ProductService:
    """
    Business logic for product operations.
    Handles validation, creation, filtering, and AI document generation.
    """
    
    @staticmethod
    def validate_category_exists(category_id):
        """
        Validate that a category exists.
        
        Args:
            category_id: UUID of the category
            
        Returns:
            Category object if exists
            
        Raises:
            ValidationError if category doesn't exist
        """
        try:
            category = Category.objects.get(id=category_id)
            return category
        except Category.DoesNotExist:
            raise ValidationError(f"Category with ID {category_id} does not exist")
    
    @staticmethod
    @transaction.atomic
    def create_product(title, description, category_id, price, currency='USD', 
                      brand=None, stock_quantity=0, is_active=True, attributes=None):
        """
        Create a product with attributes.
        
        Business logic:
        1. Validate category exists
        2. Create product row
        3. Add attributes (if provided)
        4. Return product with metadata
        
        Args:
            title: Product title
            description: Product description
            category_id: Category UUID
            price: Product price
            currency: Currency code (default: USD)
            brand: Brand name (optional)
            stock_quantity: Stock available (default: 0)
            is_active: Active status (default: True)
            attributes: List of dicts with 'key' and 'value' (optional)
            
        Returns:
            Product instance
            
        Raises:
            ValidationError if category doesn't exist
        """
        # 1. Validate category exists
        category = ProductService.validate_category_exists(category_id)
        
        # 2. Create product
        product = Product.objects.create(
            title=title,
            description=description,
            brand=brand,
            category=category,
            price=price,
            currency=currency,
            stock_quantity=stock_quantity,
            is_active=is_active
        )
        
        # 3. Add attributes if provided
        if attributes:
            ProductService.add_attributes(product, attributes)
        
        # 4. Trigger AI document generation
        ProductService.trigger_ai_document_generation(product)
        
        return product
    
    @staticmethod
    def add_attributes(product, attributes):
        """
        Add key-value attributes to a product with bulk create optimization.
        
        Performance:
        - Uses bulk_create to insert multiple attributes in single query
        - ignore_conflicts=True prevents duplicate key errors
        - Single DB write instead of N individual inserts
        
        Database Indexes Used:
        - ProductAttribute.product_id (FK index)
        - ProductAttribute.product_id + key (composite unique constraint)
        
        Args:
            product: Product instance
            attributes: List of dicts [{'key': 'color', 'value': 'red'}, ...]
        """
        if not attributes:
            return
        
        attribute_objects = [
            ProductAttribute(product=product, key=attr['key'], value=attr['value'])
            for attr in attributes
        ]
        # Single bulk insert - O(1) database roundtrip instead of N
        ProductAttribute.objects.bulk_create(attribute_objects, ignore_conflicts=True)
    
    @staticmethod
    def update_product(product, **kwargs):
        """
        Update product fields and trigger AI regeneration if needed.
        
        Args:
            product: Product instance
            **kwargs: Fields to update (title, description, price, etc.)
        """
        # Check if content-related fields changed
        content_changed = any(
            field in kwargs for field in ['title', 'description', 'brand', 'price']
        )
        
        # Update fields
        for field, value in kwargs.items():
            if hasattr(product, field):
                setattr(product, field, value)
        
        product.save()
        
        # Regenerate AI document if content changed
        if content_changed:
            ProductService.trigger_ai_document_generation(product)
    
    @staticmethod
    def trigger_ai_document_generation(product):
        """
        Trigger AI document generation for a product.
        This would normally call a Celery task.
        For now, we'll create a placeholder AIDocument.
        
        Args:
            product: Product instance
        """
        # Generate text content for LLM
        text_content = ProductService.generate_product_text(product)
        
        # Store AI document
        AIDocument.objects.update_or_create(
            source_type='product',
            source_id=str(product.id),
            defaults={
                'text_content': text_content,
                'metadata_json': {
                    'product_title': product.title,
                    'category': product.category.name,
                    'price': float(product.price),
                    'currency': product.currency,
                    'rating': product.rating_avg,
                    'in_stock': product.stock_quantity > 0,
                }
            }
        )
        
        # TODO: Queue async task for embedding generation
        # tasks.generate_product_embeddings.delay(str(product.id))
    
    @staticmethod
    def generate_product_text(product):
        """
        Convert product data to LLM-readable text.
        This is the ONLY text LLM will read about this product.
        
        Args:
            product: Product instance
            
        Returns:
            Formatted text for LLM
        """
        # Build attributes string
        attributes_text = ""
        if product.attributes.exists():
            attrs = product.attributes.all()
            attributes_text = "\n".join([f"- {attr.key}: {attr.value}" for attr in attrs])
        
        # Build text content
        text = f"""
PRODUCT: {product.title}
BRAND: {product.brand or 'Unknown'}
CATEGORY: {product.category.name}
PRICE: {product.currency} {product.price}
STOCK: {'In stock' if product.stock_quantity > 0 else 'Out of stock'}
RATING: {product.rating_avg}/5.0 ({product.rating_count} reviews)

DESCRIPTION:
{product.description}

SPECIFICATIONS:
{attributes_text if attributes_text else 'No specifications available'}
"""
        return text.strip()
    
    @staticmethod
    def filter_products(queryset, filters):
        """
        Apply filters to product queryset.
        
        Supported filters:
        - category: Category slug or UUID
        - price_min / price_max: Price range
        - brand: Brand name
        - in_stock: Boolean
        - search: Title/description search
        - rating_min: Minimum rating
        
        Args:
            queryset: Product queryset
            filters: Dict of filter parameters
            
        Returns:
            Filtered queryset
        """
        if not filters:
            return queryset
        
        # Category filter - try slug first, then ID
        if 'category' in filters:
            category_value = filters['category']
            # Try slug first (most common)
            category_filter = queryset.filter(category__slug=category_value)
            if not category_filter.exists():
                # Fall back to UUID/ID lookup
                try:
                    category_filter = queryset.filter(category__id=category_value)
                except (ValueError, TypeError):
                    # Invalid ID format, skip this filter
                    category_filter = queryset
            queryset = category_filter
        
        # Price range filter
        if 'price_min' in filters:
            queryset = queryset.filter(price__gte=filters['price_min'])
        if 'price_max' in filters:
            queryset = queryset.filter(price__lte=filters['price_max'])
        
        # Brand filter
        if 'brand' in filters:
            queryset = queryset.filter(brand__iexact=filters['brand'])
        
        # Stock filter
        if 'in_stock' in filters:
            in_stock_value = str(filters['in_stock']).lower()
            if in_stock_value in ['true', '1', 'yes']:
                queryset = queryset.filter(stock_quantity__gt=0)
        
        # Rating filter
        if 'rating_min' in filters:
            queryset = queryset.filter(rating_avg__gte=filters['rating_min'])
        
        # Search filter
        if 'search' in filters:
            search_term = filters['search']
            queryset = queryset.filter(
                title__icontains=search_term
            ) | queryset.filter(
                description__icontains=search_term
            ) | queryset.filter(
                brand__icontains=search_term
            )
        
        return queryset
