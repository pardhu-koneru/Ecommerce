from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom admin for the User model (email-based auth).
    Extends Django's built-in UserAdmin so password hashing,
    password change forms, and permissions all work correctly.
    """
    list_display = ('email', 'username', 'is_staff', 'is_active', 'created_at')
    list_filter = ('is_staff', 'is_active', 'email_verified')
    search_fields = ('email', 'username', 'phone_number')
    ordering = ('-created_at',)

    # Override fieldsets since our User doesn't have first_name/last_name
    # in the same way Django's default User does
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('username', 'first_name', 'last_name', 'phone_number')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'email_verified', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_staff', 'is_active'),
        }),
    )