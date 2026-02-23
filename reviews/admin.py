from django.contrib import admin
from .models import Review, ReviewEmbedding


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'user', 'rating', 'title', 'created_at')
    list_filter = ('rating', 'created_at', 'product')
    search_fields = ('title', 'text', 'user__email', 'product__title')
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Review Info', {
            'fields': ('id', 'product', 'user', 'rating', 'title', 'text')
        }),
        ('Engagement', {
            'fields': ('helpful_count',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ReviewEmbedding)
class ReviewEmbeddingAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'review_count', 'avg_rating', 'is_outdated', 'updated_at')
    list_filter = ('is_outdated', 'updated_at', 'avg_rating')
    search_fields = ('product__title', 'summary')
    readonly_fields = ('id', 'summary', 'embedding', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Product', {
            'fields': ('product',)
        }),
        ('Summary & Embedding', {
            'fields': ('summary', 'embedding')
        }),
        ('Statistics', {
            'fields': ('review_count', 'avg_rating', 'is_outdated')
        }),
        ('Metadata', {
            'fields': ('metadata_json',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

