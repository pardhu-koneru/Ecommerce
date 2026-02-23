from django.apps import AppConfig


class ReviewsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'reviews'
    verbose_name = 'Product Reviews & Embeddings'
    
    def ready(self):
        """
        Initialize reviews app.
        Import signals if needed for future extensions.
        """
        # import reviews.signals  # Uncomment if signals are added later
        pass

