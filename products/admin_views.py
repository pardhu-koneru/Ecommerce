from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema

from .models import Product, ProductAttribute, ProductImage
from .serializers import (
    ProductSerializer,
    CreateUpdateProductSerializer,
    AddAttributesSerializer,
    UploadProductImageSerializer,
    ProductDetailSerializer
)
from .permissions import IsAdmin
from .services import ProductService


class AdminProductManagementViewSet(ModelViewSet):
    """
    Full CRUD operations for admin users to manage products.
    Only accessible to staff/admin users.
    """
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    lookup_field = 'id'

    def get_queryset(self):
        """Return all products (including inactive) with optimized queries"""
        return Product.objects.all().prefetch_related(
            'attributes',  # Reduces N+1 queries when accessing attributes
            'images'       # Reduces N+1 queries when accessing images
        )

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CreateUpdateProductSerializer
        return ProductSerializer

    @extend_schema(description="List all products including inactive ones (admin only)")
    def list(self, request, *args, **kwargs):
        """Get all products with filters"""
        queryset = self.get_queryset()
        
        # Filter by active status if provided
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Filter by category if provided
        category_id = request.query_params.get('category_id')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
        description="Create a new product (admin only)",
        request=CreateUpdateProductSerializer,
        responses={201: ProductSerializer}
    )
    def create(self, request, *args, **kwargs):
        """
        Create a new product with attributes.
        
        Business logic in service:
        1. Validate category exists
        2. Create product row
        3. Add attributes
        4. Generate AI document
        """
        serializer = CreateUpdateProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            product = ProductService.create_product(
                title=serializer.validated_data['title'],
                description=serializer.validated_data['description'],
                category_id=serializer.validated_data['category'].id,
                price=serializer.validated_data['price'],
                currency=serializer.validated_data.get('currency', 'USD'),
                brand=serializer.validated_data.get('brand'),
                stock_quantity=serializer.validated_data.get('stock_quantity', 0),
                is_active=serializer.validated_data.get('is_active', True),
                attributes=serializer.validated_data.get('attributes'),
            )
            
            return Response(
                ProductSerializer(product).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @extend_schema(description="Get a specific product by ID (admin only)")
    def retrieve(self, request, *args, **kwargs):
        """Get product details by ID"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        description="Update a product completely (admin only)",
        request=CreateUpdateProductSerializer,
        responses={200: ProductSerializer}
    )
    def update(self, request, *args, **kwargs):
        """Update product details"""
        product = self.get_object()
        serializer = CreateUpdateProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        ProductService.update_product(product, **serializer.validated_data)
        return Response(
            ProductSerializer(product).data,
            status=status.HTTP_200_OK
        )

    @extend_schema(
        description="Partially update a product (admin only)",
        request=CreateUpdateProductSerializer,
        responses={200: ProductSerializer}
    )
    def partial_update(self, request, *args, **kwargs):
        """Partially update product details"""
        product = self.get_object()
        serializer = CreateUpdateProductSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        ProductService.update_product(product, **serializer.validated_data)
        return Response(
            ProductSerializer(product).data,
            status=status.HTTP_200_OK
        )

    @extend_schema(description="Delete a product (admin only)")
    def destroy(self, request, *args, **kwargs):
        """Delete a product"""
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        description="Add attributes to a product (admin only)",
        request=AddAttributesSerializer,
        responses={200: ProductSerializer}
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdmin])
    def add_attributes(self, request, id=None):
        """Add attributes to a product"""
        serializer = AddAttributesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            product = self.get_object()
            # Convert dict to list of dicts for service
            attributes = [
                {'key': k, 'value': v} 
                for k, v in serializer.validated_data['attributes'].items()
            ]
            
            ProductService.add_attributes(product, attributes)
            
            # Return updated product with attributes
            product.refresh_from_db()
            return Response(
                ProductDetailSerializer(product).data,
                status=status.HTTP_200_OK
            )
        except Product.DoesNotExist:
            return Response(
                {'detail': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @extend_schema(
        description="Upload product image (admin only)",
        request=UploadProductImageSerializer
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdmin])
    def upload_image(self, request, id=None):
        """Upload an image for a product"""
        serializer = UploadProductImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            product = self.get_object()
            image_file = serializer.validated_data['image']
            alt_text = serializer.validated_data.get('alt_text', '')
            is_primary = serializer.validated_data.get('is_primary', False)
            
            product_image = ProductImage.objects.create(
                product=product,
                image=image_file,
                alt_text=alt_text,
                is_primary=is_primary
            )
            
            return Response(
                {'detail': 'Image uploaded successfully', 'image_id': str(product_image.id)},
                status=status.HTTP_201_CREATED
            )
        except Product.DoesNotExist:
            return Response(
                {'detail': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @extend_schema(description="Activate/Deactivate a product (admin only)")
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdmin])
    def toggle_active(self, request, id=None):
        """Toggle product active status"""
        try:
            product = self.get_object()
            product.is_active = not product.is_active
            product.save()
            
            return Response(
                {
                    'detail': f"Product {'activated' if product.is_active else 'deactivated'} successfully",
                    'is_active': product.is_active
                },
                status=status.HTTP_200_OK
            )
        except Product.DoesNotExist:
            return Response(
                {'detail': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @extend_schema(description="Get product statistics (admin only)")
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsAdmin])
    def stats(self, request):
        """Get product statistics"""
        total = Product.objects.count()
        active = Product.objects.filter(is_active=True).count()
        in_stock = Product.objects.filter(stock_quantity__gt=0).count()
        avg_rating = Product.objects.filter(rating_count__gt=0).values('rating_avg').count()
        
        return Response({
            'total_products': total,
            'active_products': active,
            'in_stock_products': in_stock,
            'products_with_ratings': avg_rating,
        })
