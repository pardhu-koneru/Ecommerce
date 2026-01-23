
# Create your views here.
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .serializers import RegisterSerializer, UserSerializer, VerifyEmailSerializer, ResendVerificationEmailSerializer, LogoutSerializer
from .services import EmailVerificationService, LogoutService
from .tokens import CustomRefreshToken

class AuthViewSet(ViewSet):
    serializer_class = RegisterSerializer
    
    @extend_schema(request=TokenObtainPairSerializer)
    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def login(self, request):
        """
        Authenticate user and issue tokens.
        
        On successful login:
        - Restore token validity (is_token_revoked=False)
        - Issue new tokens with current revocation status
        """
        serializer = TokenObtainPairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.user
        
        # Restore token validity on login
        LogoutService.restore_tokens(user)
        
        # Generate tokens with current revocation status
        refresh = CustomRefreshToken.for_user(user)
        
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }, status=200)
    
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
    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
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
    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
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

    @extend_schema(request=LogoutSerializer)
    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """Logout user by incrementing token_version"""
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh_token = serializer.validated_data['refresh']
        
        # Use service to logout (increments token_version)
        success, message, status_code = LogoutService.logout_user(request.user, refresh_token)
        
        if success:
            return Response({"msg": message}, status=status_code)
        else:
            return Response({"error": message}, status=status_code)


class UserViewSet(ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    @extend_schema(responses=UserSerializer)
    def list(self, request):
        return Response({"msg": "User dashboard"})