from django.contrib import admin
from .models import User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'username', 'is_staff', 'is_active', 'created_at')
    list_filter = ('is_staff', 'is_active', 'email_verified')
    search_fields = ('email', 'username', 'phone_number')
    ordering = ('-created_at',)