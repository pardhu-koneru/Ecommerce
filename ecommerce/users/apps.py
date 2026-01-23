from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = 'users'
    
    def ready(self):
        # Import schema extensions so drf-spectacular discovers them
        import users.schema
