from rest_framework.routers import DefaultRouter
from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import AuthViewSet, UserViewSet

router = DefaultRouter()
router.register("auth", AuthViewSet, basename="auth")
router.register("user", UserViewSet, basename="user")

urlpatterns = [
    path("login/", TokenObtainPairView.as_view()),
    path("refresh/", TokenRefreshView.as_view()),
]

urlpatterns += router.urls
