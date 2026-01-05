from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema

from .serializers import MakeStaffSerializer
from .models import User


class AdminViewSet(ViewSet):
    permission_classes = [IsAdminUser]

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
