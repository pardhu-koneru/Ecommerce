from rest_framework.routers import DefaultRouter
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import AuthViewSet, UserViewSet
from .admin_views import AdminUserManagementViewSet, AdminViewSet

router = DefaultRouter()
router.register("auth", AuthViewSet, basename="auth")
router.register("user", UserViewSet, basename="user")
router.register("admin/users", AdminUserManagementViewSet, basename="admin-users")

urlpatterns = [
    path("refresh/", TokenRefreshView.as_view()),
] + router.urls
