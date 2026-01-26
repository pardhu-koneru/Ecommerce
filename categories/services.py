from django.db.models import Count
from .models import Category


class CategoryService:
    """Service for handling category business logic"""

    @staticmethod
    def get_stats():
        """Get category statistics"""
        return {
            'total_categories': Category.objects.count(),
            'active_categories': Category.objects.filter(is_active=True).count(),
            'root_categories': Category.objects.filter(parent__isnull=True).count(),
            'categories_with_children': Category.objects.annotate(
                children_count=Count('children')
            ).filter(children_count__gt=0).count(),
        }

    @staticmethod
    def get_category_tree():
        """Get category hierarchy tree"""
        root_categories = Category.objects.filter(parent__isnull=True, is_active=True)
        tree = []
        
        for category in root_categories:
            tree.append(CategoryService._build_tree_node(category))
        
        return tree

    @staticmethod
    def _build_tree_node(category):
        """Build a single node of the category tree"""
        return {
            'id': str(category.id),
            'name': category.name,
            'slug': category.slug,
            'children': [
                CategoryService._build_tree_node(child)
                for child in category.children.filter(is_active=True)
            ]
        }

    @staticmethod
    def deactivate_category_and_children(category):
        """Deactivate a category and all its children"""
        category.is_active = False
        category.save()
        
        for child in category.children.all():
            CategoryService.deactivate_category_and_children(child)
