
# Create your views here.
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema

from .serializers import RegisterSerializer, UserSerializer, VerifyEmailSerializer, ResendVerificationEmailSerializer
from .services import EmailVerificationService

class AuthViewSet(ViewSet):
    
    @extend_schema(request=RegisterSerializer)
    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Create verification token via service
        token = EmailVerificationService.create_verification_token(user)
        
        # TODO: Send email with verification link
        # email_body = f"Click here to verify: http://yourfrontend.com/verify?token={token.token}"
        # send_email(user.email, "Verify your email", email_body)
        
        return Response({
            "msg": "User registered. Check your email for verification link.",
            "token": token.token  # In production, don't return this. Only send via email.
        }, status=201)

    @extend_schema(responses=UserSerializer)
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def me(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    @extend_schema(request=VerifyEmailSerializer)
    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def verify_email(self, request):
        """Verify email using token"""
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token_str = serializer.validated_data['token']
        
        # Use service to verify email
        success, message, status_code = EmailVerificationService.verify_email_with_token(token_str)
        
        if success:
            return Response({"msg": message}, status=status_code)
        else:
            return Response({"error": message}, status=status_code)

    @extend_schema(request=ResendVerificationEmailSerializer)
    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def resend_verification_email(self, request):
        """Resend verification email"""
        serializer = ResendVerificationEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        
        # Use service to resend email
        success, message, status_code, token = EmailVerificationService.resend_verification_email(email)
        
        if success:
            return Response({"msg": message}, status=status_code)
        else:
            return Response({"error": message}, status=status_code)


class UserViewSet(ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        return Response({"msg": "User dashboard"})