from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

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
from .tasks import generate_ai_document_for_product, batch_generate_ai_documents


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
        # For actions with no request body, return None so drf-spectacular
        # doesn't auto-generate a requestBody from ProductSerializer.
        # The @extend_schema(request=None) on each action handles the schema.
        if self.action in ['process_ai', 'toggle_active', 'ai_status', 'batch_ai_status']:
            return None
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

    @extend_schema(
        description="Activate/Deactivate a product (admin only)",
        request=None,
        responses={200: {'description': 'Product activation toggled'}}
    )
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

    @extend_schema(
        description="Process product images and generate AI document with embeddings (async)",
        parameters=[
            OpenApiParameter(
                name='id',
                location=OpenApiParameter.PATH,
                description='Product UUID',
                required=True,
                type=OpenApiTypes.UUID
            )
        ],
        request=None,
        responses={202: {'description': 'Task enqueued'}}
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdmin])
    def process_ai(self, request, id=None):
        """
        Async endpoint to process product with AI:
        Takes product ID from URL path (no request body needed).
        
        1. Extract vision descriptions from images (< 10 lines each)
        2. Combine with product specs text
        3. Generate embeddings
        4. Store in vector database
        
        Returns immediately with task ID for polling.
        URL: POST /api/admin/products/{product_id}/process_ai/
        """
        try:
            product = self.get_object()
            
            # Enqueue async task
            task = generate_ai_document_for_product.delay(str(product.id))
            
            return Response(
                {
                    'status': 'processing',
                    'message': f'AI processing started for {product.title}',
                    'task_id': task.id,
                    'product_id': str(product.id),
                    'check_status_url': f'/api/admin/products/{product.id}/ai_status/?task_id={task.id}'
                },
                status=status.HTTP_202_ACCEPTED
            )
        except Product.DoesNotExist:
            return Response(
                {'detail': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @extend_schema(
        description="Check AI processing task status",
        parameters=[
            OpenApiParameter(
                name='id',
                location=OpenApiParameter.PATH,
                description='Product UUID',
                required=True,
                type=OpenApiTypes.UUID
            ),
            OpenApiParameter(
                name='task_id',
                location=OpenApiParameter.QUERY,
                description='Celery task ID from process_ai response',
                required=True,
                type=OpenApiTypes.STR
            )
        ]
    )
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated, IsAdmin])
    def ai_status(self, request, id=None):
        """
        Check the status of an AI processing task.
        
        Query params:
        - task_id: Celery task ID
        """
        from celery.result import AsyncResult
        
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response(
                {'detail': 'task_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            task = AsyncResult(task_id)
            
            if task.state == 'PENDING':
                return Response({'status': 'pending', 'message': 'Task is waiting to be processed'})
            elif task.state == 'STARTED':
                return Response({'status': 'processing', 'message': 'Task is currently processing'})
            elif task.state == 'SUCCESS':
                return Response({
                    'status': 'completed',
                    'result': task.result,
                    'message': 'AI processing completed successfully'
                })
            elif task.state == 'FAILURE':
                return Response({
                    'status': 'failed',
                    'error': str(task.info),
                    'message': 'AI processing failed'
                }, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'status': task.state, 'message': f'Task state: {task.state}'})
        
        except Exception as e:
            return Response(
                {'detail': f'Error checking task status: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @extend_schema(
        description="Batch process multiple products with AI (async)",
        request={
            'type': 'object',
            'properties': {
                'product_ids': {
                    'type': 'array',
                    'items': {'type': 'string', 'format': 'uuid'},
                    'description': 'List of product UUIDs to process'
                }
            },
            'required': ['product_ids']
        },
        responses={202: {'description': 'Batch task enqueued'}}
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsAdmin])
    def batch_process_ai(self, request):
        """
        Async endpoint to batch process multiple products.
        
        Request body:
        {
            "product_ids": ["uuid1", "uuid2", ...]
        }
        
        Returns task ID for monitoring batch progress.
        """
        product_ids = request.data.get('product_ids', [])
        
        if not product_ids:
            return Response(
                {'detail': 'product_ids list is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate all products exist
        products = Product.objects.filter(id__in=product_ids)
        if products.count() != len(product_ids):
            return Response(
                {'detail': f'Only {products.count()} of {len(product_ids)} products found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Enqueue batch task
            result = batch_generate_ai_documents.delay(product_ids)
            
            return Response(
                {
                    'status': 'batch_processing',
                    'message': f'AI batch processing started for {len(product_ids)} products',
                    'task_id': result.id,
                    'product_count': len(product_ids),
                    'check_status_url': f'/api/admin/products/batch_ai_status/?task_id={result.id}'
                },
                status=status.HTTP_202_ACCEPTED
            )
        except Exception as e:
            return Response(
                {'detail': f'Error starting batch processing: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @extend_schema(
        description="Check batch AI processing status",
        parameters=[
            OpenApiParameter(
                name='task_id',
                location=OpenApiParameter.QUERY,
                description='Celery group task ID from batch_process_ai response',
                required=True,
                type=OpenApiTypes.STR
            )
        ]
    )
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsAdmin])
    def batch_ai_status(self, request):
        """
        Check the status of a batch AI processing task.
        
        Query params:
        - task_id: Celery task ID from batch_process_ai response
        """
        from celery.result import AsyncResult
        
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response(
                {'detail': 'task_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            task = AsyncResult(task_id)
            
            if task.state == 'PENDING':
                return Response({'status': 'pending', 'message': 'Batch task is waiting'})
            elif task.state == 'STARTED':
                return Response({'status': 'processing', 'message': 'Batch task is processing'})
            elif task.state == 'SUCCESS':
                return Response({
                    'status': 'completed',
                    'result': task.result,
                    'message': 'Batch processing completed'
                })
            elif task.state == 'FAILURE':
                return Response({
                    'status': 'failed',
                    'error': str(task.info),
                }, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'status': task.state})
        
        except Exception as e:
            return Response(
                {'detail': f'Error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
