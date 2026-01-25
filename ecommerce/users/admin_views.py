from rest_framework.viewsets import ViewSet, ModelViewSet
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import extend_schema

from .serializers import MakeStaffSerializer, AdminUserSerializer
from .models import User


class AdminUserPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class AdminUserManagementViewSet(ModelViewSet):
    """
    Admin CRUD endpoints for user management.
    All operations require admin permission.
    """
    queryset = User.objects.all()
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]
    pagination_class = AdminUserPagination
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['email', 'username', 'first_name', 'last_name']
    ordering_fields = ['created_at', 'email', 'is_active', 'is_staff']
    ordering = ['-created_at']

    @extend_schema(description="List all users with pagination and filtering")
    def list(self, request, *args, **kwargs):
        """GET /api/admin/users/ - List all users (paginated, filterable)"""
        return super().list(request, *args, **kwargs)

    @extend_schema(description="Get detailed information about a specific user")
    def retrieve(self, request, *args, **kwargs):
        """GET /api/admin/users/{id}/ - Get user details"""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(request=AdminUserSerializer, description="Create a new user account")
    def create(self, request, *args, **kwargs):
        """POST /api/admin/users/ - Create new user"""
        return super().create(request, *args, **kwargs)

    @extend_schema(request=AdminUserSerializer, description="Update all user fields")
    def update(self, request, *args, **kwargs):
        """PUT /api/admin/users/{id}/ - Update user details"""
        return super().update(request, *args, **kwargs)

    @extend_schema(request=AdminUserSerializer, description="Partially update user fields")
    def partial_update(self, request, *args, **kwargs):
        """PATCH /api/admin/users/{id}/ - Update user details"""
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(description="Delete a user account")
    def destroy(self, request, *args, **kwargs):
        """DELETE /api/admin/users/{id}/ - Delete user"""
        return super().destroy(request, *args, **kwargs)

    @extend_schema(description="Activate a deactivated user account")
    @action(detail=True, methods=["patch"])
    def activate(self, request, pk=None):
        """PATCH /api/admin/users/{id}/activate/ - Activate user account"""
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response(
            {"msg": f"User {user.email} has been activated"},
            status=status.HTTP_200_OK
        )

    @extend_schema(description="Deactivate an active user account")
    @action(detail=True, methods=["patch"])
    def deactivate(self, request, pk=None):
        """PATCH /api/admin/users/{id}/deactivate/ - Deactivate user account"""
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response(
            {"msg": f"User {user.email} has been deactivated"},
            status=status.HTTP_200_OK
        )


class AdminViewSet(ViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = MakeStaffSerializer

    @extend_schema(request=MakeStaffSerializer)
    @action(detail=False, methods=["post"])
    def make_staff(self, request):
        """Only admins can promote users to staff"""
        serializer = MakeStaffSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            user = User.objects.get(email=serializer.validated_data['email'])
            user.is_staff = True
            user.save()
            return Response({"msg": f"{user.email} is now a staff user"}, status=200)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)
