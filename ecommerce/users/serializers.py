from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import User, EmailVerificationToken

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    username = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["email", "username", "first_name", "last_name", "phone_number", "password"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "username", "first_name", "last_name", "phone_number", "email_verified", "role"]

    @extend_schema_field(serializers.CharField)
    def get_role(self, obj):
        return "admin" if obj.is_staff else "user"


class MakeStaffSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField()


class ResendVerificationEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

class AdminUserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["id", "email", "username", "first_name", "last_name", "phone_number", 
                  "password", "email_verified", "is_active", "is_staff", "role", "created_at"]
        read_only_fields = ["id", "created_at"]

    @extend_schema_field(serializers.CharField)
    def get_role(self, obj):
        return "admin" if obj.is_staff else "user"

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User.objects.create(**validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance