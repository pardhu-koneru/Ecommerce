from drf_spectacular.extensions import OpenApiAuthenticationExtension
from .authentication import CustomJWTAuthentication


class CustomJWTAuthenticationExtension(OpenApiAuthenticationExtension):
    """
    Extension to make drf-spectacular recognize CustomJWTAuthentication
    Tells Swagger/OpenAPI how to handle our custom JWT authentication
    """
    target_class = CustomJWTAuthentication
    name = 'Bearer'
    
    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
        }
