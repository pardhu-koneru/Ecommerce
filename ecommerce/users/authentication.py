from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import exceptions
from .models import User
from .cache_service import TokenRevocationService


class CustomJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication with Redis-based token revocation.
    
    Intuitive flow:
    1. User logs in → Tokens issued, Redis clean
    2. User logs out → User added to Redis revocation set (TTL=access token lifetime)
    3. User makes request with access token → Check Redis (microseconds)
    4. If in Redis → Token revoked, reject (401)
    5. If not in Redis → Token valid, allow
    
    Performance: Redis lookup is 1000x faster than database query
    Scalable: Handles millions of concurrent users
    """

    def authenticate(self, request):
        # Get the JWT token and user from parent authentication
        result = super().authenticate(request)
        
        if result is None:
            return None
        
        user, validated_token = result
        
        # 🔴 CHECK REDIS (microseconds) instead of database
        # This is the key performance optimization
        if TokenRevocationService.is_token_revoked(user.id):
            raise exceptions.AuthenticationFailed(
                'Your tokens have been revoked. Please login again.'
            )
        
        return user, validated_token


