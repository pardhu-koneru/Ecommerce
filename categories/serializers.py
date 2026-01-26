from rest_framework import serializers
from .models import Category


class CategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'image', 'parent', 'parent_name', 'is_active', 'children', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_children(self, obj):
        if obj.children.exists():
            return CategorySerializer(obj.children.all(), many=True).data
        return []


class CreateUpdateCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['name', 'slug', 'description', 'image', 'parent', 'is_active']
        extra_kwargs = {
            'parent': {'required': False, 'allow_null': True}
        }

    def validate_slug(self, value):
        if not value:
            raise serializers.ValidationError("Slug cannot be empty")
        return value

    def validate_parent(self, value):
        """Validate that parent category exists"""
        if value is None:
            return value  # Parent is optional
        
        if not Category.objects.filter(id=value.id).exists():
            raise serializers.ValidationError(f"Parent category with ID {value.id} does not exist")
        
        return value


class CategoryListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'image', 'is_active']
