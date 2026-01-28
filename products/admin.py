from django.contrib import admin
from .models import Product, ProductAttribute, ProductImage, AIDocument


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('title', 'brand', 'category', 'price', 'stock_quantity', 'rating_avg', 'is_active', 'created_at')
    list_filter = ('is_active', 'category', 'created_at', 'rating_avg')
    search_fields = ('title', 'brand', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at', 'rating_avg', 'rating_count')
    ordering = ('-created_at',)


@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ('product', 'key', 'value')
    list_filter = ('key',)
    search_fields = ('product__title', 'key', 'value')


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'is_primary', 'display_order', 'created_at')
    list_filter = ('is_primary', 'created_at')
    search_fields = ('product__title', 'alt_text')


@admin.register(AIDocument)
class AIDocumentAdmin(admin.ModelAdmin):
    list_display = ('source_type', 'source_id', 'is_indexed', 'created_at')
    list_filter = ('source_type', 'is_indexed', 'created_at')
    search_fields = ('source_id', 'text_content')
    readonly_fields = ('id', 'created_at', 'updated_at')
