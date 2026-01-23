from django.core.cache import cache
from datetime import datetime, timedelta


class TokenRevocationService:
    """
    Redis-based token revocation service.
    
    Intuition:
    - When user logs out, add their user_id to Redis revocation set
    - Redis key expires automatically when access token TTL ends
    - On each request, check Redis (microseconds vs database queries)
    - No database queries needed for revocation checks
    
    Industry standard: Netflix, Uber, Auth0 use similar approach
    """
    
    # Redis key prefix for revocation tracking
    REVOCATION_KEY_PREFIX = "revoked_tokens:"
    
    @staticmethod
    def _get_revocation_key(user_id):
        """Generate unique Redis key for user's revocation status"""
        return f"{TokenRevocationService.REVOCATION_KEY_PREFIX}{user_id}"
    
    @staticmethod
    def revoke_user_tokens(user, access_token_lifetime_minutes=15):
        """
        Revoke all tokens for a user by adding to Redis revocation set.
        
        Args:
            user: User instance
            access_token_lifetime_minutes: How long to keep revocation in Redis
                                          (should match ACCESS_TOKEN_LIFETIME)
        
        Returns:
            bool: Success status
        """
        try:
            key = TokenRevocationService._get_revocation_key(user.id)
            
            # Store revocation in Redis with TTL = access token lifetime
            # After TTL expires, Redis automatically deletes the key
            timeout_seconds = access_token_lifetime_minutes * 60
            cache.set(key, True, timeout_seconds)
            
            return True
        except Exception as e:
            print(f"Error revoking tokens for user {user.id}: {str(e)}")
            return False
    
    @staticmethod
    def is_token_revoked(user_id):
        """
        Check if a user's tokens are revoked.
        
        This is a Redis lookup (microseconds), not a database query!
        
        Args:
            user_id: User ID to check
            
        Returns:
            bool: True if revoked, False if not
        """
        try:
            key = TokenRevocationService._get_revocation_key(user_id)
            return cache.get(key, False)
        except Exception as e:
            print(f"Error checking revocation status: {str(e)}")
            # Fail safely - treat as revoked if Redis is unavailable
            return True
    
    @staticmethod
    def restore_tokens(user):
        """
        Restore token validity for a user (called on login).
        
        Removes user from Redis revocation set.
        
        Args:
            user: User instance
            
        Returns:
            bool: Success status
        """
        try:
            key = TokenRevocationService._get_revocation_key(user.id)
            cache.delete(key)
            return True
        except Exception as e:
            print(f"Error restoring tokens for user {user.id}: {str(e)}")
            return False
