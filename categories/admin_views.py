from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema

from .models import Category
from .serializers import (
    CategorySerializer,
    CreateUpdateCategorySerializer,
)
from .permissions import IsAdmin
from .services import CategoryService


class AdminCategoryManagementViewSet(ModelViewSet):
    """
    Full CRUD operations for admin users to manage categories.
    Only accessible to staff/admin users.
    Admin uses slug for human-readable URLs instead of UUID.
    """
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    lookup_field = 'slug'

    def get_queryset(self):
        """Return all categories (including inactive) for admins"""
        return Category.objects.all()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return CreateUpdateCategorySerializer
        return CategorySerializer

    @extend_schema(description="List all categories including inactive ones (admin only)")
    def list(self, request, *args, **kwargs):
        """Get all categories with filters"""
        queryset = self.get_queryset()
        
        # Filter by active status if provided
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Filter by parent if provided
        parent_id = request.query_params.get('parent_id')
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(description="Get a specific category by ID (admin only)")
    def retrieve(self, request, *args, **kwargs):
        """Get category details by ID"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        description="Create a new category (admin only)",
        request=CreateUpdateCategorySerializer,
        responses={201: CategorySerializer}
    )
    def create(self, request, *args, **kwargs):
        """Create a new category"""
        return super().create(request, *args, **kwargs)

    @extend_schema(
        description="Update a category completely (admin only)",
        request=CreateUpdateCategorySerializer,
        responses={200: CategorySerializer}
    )
    def update(self, request, *args, **kwargs):
        """Update category details"""
        return super().update(request, *args, **kwargs)

    @extend_schema(
        description="Partially update a category (admin only)",
        request=CreateUpdateCategorySerializer,
        responses={200: CategorySerializer}
    )
    def partial_update(self, request, *args, **kwargs):
        """Partially update category details"""
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(description="Delete a category (admin only)")
    def destroy(self, request, *args, **kwargs):
        """Delete a category"""
        category = self.get_object()
        
        # Check if category has children
        if category.children.exists():
            return Response(
                {'detail': 'Cannot delete category with children. Delete or reassign children first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return super().destroy(request, *args, **kwargs)

    @extend_schema(description="Deactivate a category and all its children (admin only)")
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdmin])
    def deactivate(self, request, slug=None):
        """Deactivate a category and all its children"""
        try:
            category = Category.objects.get(slug=slug)
            CategoryService.deactivate_category_and_children(category)
            serializer = self.get_serializer(category)
            return Response(
                {'detail': 'Category and all children deactivated successfully', 'data': serializer.data},
                status=status.HTTP_200_OK
            )
        except Category.DoesNotExist:
            return Response(
                {'detail': 'Category not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @extend_schema(description="Activate a category (admin only)")
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsAdmin])
    def activate(self, request, slug=None):
        """Activate a category"""
        try:
            category = Category.objects.get(slug=slug)
            category.is_active = True
            category.save()
            serializer = self.get_serializer(category)
            return Response(
                {'detail': 'Category activated successfully', 'data': serializer.data},
                status=status.HTTP_200_OK
            )
        except Category.DoesNotExist:
            return Response(
                {'detail': 'Category not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @extend_schema(description="Get detailed category statistics (admin only)")
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsAdmin])
    def stats(self, request):
        """Get detailed category statistics"""
        stats = CategoryService.get_stats()
        return Response(stats)

    @extend_schema(description="Get category hierarchy tree (admin only)")
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsAdmin])
    def tree(self, request):
        """Get full category hierarchy tree"""
        tree = CategoryService.get_category_tree()
        return Response({'tree': tree})
