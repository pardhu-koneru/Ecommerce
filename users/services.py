from django.utils import timezone
from rest_framework import status
from .models import User, EmailVerificationToken
from .cache_service import TokenRevocationService


class EmailVerificationService:
    """Service for handling email verification logic"""

    @staticmethod
    def create_verification_token(user):
        """
        Create a verification token for a user
        Deletes old token if it exists
        """
        EmailVerificationToken.objects.filter(user=user).delete()
        token = EmailVerificationToken.objects.create(user=user)
        return token

    @staticmethod
    def verify_email_with_token(token_str):
        """
        Verify email using token
        Returns: (success: bool, message: str, status_code: int)
        """
        try:
            token = EmailVerificationToken.objects.get(token=token_str)

            if token.is_expired():
                return (
                    False,
                    "Token has expired. Request a new verification email.",
                    status.HTTP_400_BAD_REQUEST,
                )

            # Mark email as verified
            token.user.email_verified = True
            token.user.save()

            # Delete token
            token.delete()

            return (
                True,
                "Email verified successfully!",
                status.HTTP_200_OK,
            )
        except EmailVerificationToken.DoesNotExist:
            return (
                False,
                "Invalid token",
                status.HTTP_400_BAD_REQUEST,
            )

    @staticmethod
    def resend_verification_email(email):
        """
        Resend verification email to user
        Returns: (success: bool, message: str, status_code: int, token: str or None)
        """
        try:
            user = User.objects.get(email=email)

            if user.email_verified:
                return (
                    True,
                    "Email already verified",
                    status.HTTP_200_OK,
                    None,
                )

            # Delete old token and create new one
            token = EmailVerificationService.create_verification_token(user)

            return (
                True,
                "Verification email sent",
                status.HTTP_200_OK,
                token.token,
            )
        except User.DoesNotExist:
            return (
                False,
                "User not found",
                status.HTTP_404_NOT_FOUND,
                None,
            )


class LogoutService:
    """
    Service for handling user logout via Redis token revocation.
    
    When a user logs out, we add them to Redis revocation set.
    Redis automatically removes the entry when access token TTL expires.
    This is 1000x faster than database lookups.
    """

    @staticmethod
    def logout_user(user, refresh_token=None):
        """
        Revoke all tokens for a user using Redis.
        
        Args:
            user: User instance
            refresh_token: Optional, for audit logging
            
        Returns:
            (success: bool, message: str, status_code: int)
        """
        try:
            # Add user to Redis revocation set
            TokenRevocationService.revoke_user_tokens(user)
            
            return (
                True,
                "Logged out successfully. All tokens revoked.",
                status.HTTP_200_OK,
            )
        except Exception as e:
            return (
                False,
                "Error logging out",
                status.HTTP_400_BAD_REQUEST,
            )
    
    @staticmethod
    def restore_tokens(user):
        """
        Restore token validity for a user (called on successful login).
        
        Removes user from Redis revocation set.
        
        Args:
            user: User instance
        """
        TokenRevocationService.restore_tokens(user)
