from rest_framework_simplejwt.tokens import RefreshToken


class CustomRefreshToken(RefreshToken):
    """
    Standard refresh token.
    
    With Redis-based revocation, we don't need to embed revocation status.
    Redis handles revocation checks independently.
    """
    pass


