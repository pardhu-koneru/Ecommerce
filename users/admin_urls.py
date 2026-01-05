from rest_framework.routers import DefaultRouter
from .admin_views import AdminViewSet

router = DefaultRouter()
router.register("admin", AdminViewSet, basename="admin")

urlpatterns = router.urls
