"""
Django management command to populate database with test data.
Creates categories, products, and reviews.

Usage:
    python manage.py populate_reviews_data
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from categories.models import Category
from products.models import Product
from reviews.models import Review
from decimal import Decimal
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'Populate database with electronics categories, products, and reviews'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting data population...'))

        # Create test users if they don't exist
        users = self._create_users()
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(users)} test users'))

        # Create electronics category
        electronics_cat = self._create_electronics_category()
        self.stdout.write(self.style.SUCCESS(f'✓ Created Electronics category'))

        # Create subcategories
        subcategories = self._create_subcategories(electronics_cat)
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(subcategories)} subcategories'))

        # Create products
        products = self._create_products(subcategories)
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(products)} products'))

        # Create reviews
        review_count = self._create_reviews(products, users)
        self.stdout.write(self.style.SUCCESS(f'✓ Created {review_count} reviews'))

        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('Data population complete!'))
        self.stdout.write(self.style.SUCCESS('='*60))

    @staticmethod
    def _create_users():
        """Create test users."""
        user_data = [
            {'email': 'john@example.com', 'username': 'john_doe', 'first_name': 'John', 'last_name': 'Doe'},
            {'email': 'jane@example.com', 'username': 'jane_smith', 'first_name': 'Jane', 'last_name': 'Smith'},
            {'email': 'alice@example.com', 'username': 'alice_wonder', 'first_name': 'Alice', 'last_name': 'Wonder'},
            {'email': 'bob@example.com', 'username': 'bob_builder', 'first_name': 'Bob', 'last_name': 'Builder'},
            {'email': 'carol@example.com', 'username': 'carol_ross', 'first_name': 'Carol', 'last_name': 'Ross'},
            {'email': 'david@example.com', 'username': 'david_wilson', 'first_name': 'David', 'last_name': 'Wilson'},
        ]

        users = []
        for data in user_data:
            user, created = User.objects.get_or_create(
                email=data['email'],
                defaults={
                    'username': data['username'],
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                    'email_verified': True,
                }
            )
            if created:
                user.set_password('testpass123')
                user.save()
            users.append(user)

        return users

    @staticmethod
    def _create_electronics_category():
        """Create Electronics main category."""
        category, created = Category.objects.get_or_create(
            name='Electronics',
            slug='electronics',
            defaults={'description': 'Electronic devices and gadgets'}
        )
        return category

    @staticmethod
    def _create_subcategories(parent_category):
        """Create electronics subcategories."""
        subcategories_data = [
            {'name': 'Laptops', 'slug': 'laptops', 'description': 'Portable computers and laptops'},
            {'name': 'Smartphones', 'slug': 'smartphones', 'description': 'Mobile phones and smartphones'},
            {'name': 'Tablets', 'slug': 'tablets', 'description': 'Tablets and iPad devices'},
            {'name': 'Accessories', 'slug': 'accessories', 'description': 'Tech accessories and peripherals'},
            {'name': 'Audio', 'slug': 'audio', 'description': 'Headphones, speakers, and audio devices'},
        ]

        subcategories = []
        for data in subcategories_data:
            category, created = Category.objects.get_or_create(
                name=data['name'],
                slug=data['slug'],
                defaults={
                    'description': data['description'],
                    'parent': parent_category
                }
            )
            subcategories.append(category)

        return subcategories

    @staticmethod
    def _create_products(subcategories):
        """Create products."""
        products_data = [
            # Laptops
            {
                'title': 'MacBook Pro 16" M3 Max',
                'category_slug': 'laptops',
                'description': 'Apple MacBook Pro with M3 Max chip, 36GB RAM, 1TB SSD. Perfect for professionals and designers.',
                'brand': 'Apple',
                'price': Decimal('3499.99'),
                'stock': 15,
            },
            {
                'title': 'Dell Inspiron 15 (2024)',
                'category_slug': 'laptops',
                'description': 'Dell Inspiron with Intel Core i7, 16GB RAM, 512GB SSD. Great for gaming and productivity.',
                'brand': 'Dell',
                'price': Decimal('899.99'),
                'stock': 25,
            },
            {
                'title': 'Lenovo ThinkPad X1 Carbon',
                'category_slug': 'laptops',
                'description': 'Lenovo ThinkPad X1 Carbon Gen 11 - Business laptop with Intel Core i7, 16GB RAM, 512GB SSD.',
                'brand': 'Lenovo',
                'price': Decimal('1399.99'),
                'stock': 20,
            },
            {
                'title': 'HP Pavilion 15',
                'category_slug': 'laptops',
                'description': 'HP Pavilion 15 with AMD Ryzen 5, 8GB RAM, 256GB SSD. Budget-friendly option.',
                'brand': 'HP',
                'price': Decimal('549.99'),
                'stock': 30,
            },
            # Smartphones
            {
                'title': 'iPhone 15 Pro Max',
                'category_slug': 'smartphones',
                'description': 'Apple iPhone 15 Pro Max with A17 Pro chip, 256GB storage. The latest flagship phone.',
                'brand': 'Apple',
                'price': Decimal('1199.99'),
                'stock': 40,
            },
            {
                'title': 'Samsung Galaxy S24 Ultra',
                'category_slug': 'smartphones',
                'description': 'Samsung Galaxy S24 Ultra with Snapdragon 8 Gen 3, 12GB RAM, 256GB storage.',
                'brand': 'Samsung',
                'price': Decimal('1299.99'),
                'stock': 35,
            },
            {
                'title': 'Google Pixel 9 Pro',
                'category_slug': 'smartphones',
                'description': 'Google Pixel 9 Pro with Tensor G4, 12GB RAM, 256GB storage. Better camera with AI.',
                'brand': 'Google',
                'price': Decimal('999.99'),
                'stock': 25,
            },
            {
                'title': 'OnePlus 13',
                'category_slug': 'smartphones',
                'description': 'OnePlus 13 with Snapdragon 8 Gen 3, 12GB RAM, 256GB storage. Fast charging battery.',
                'brand': 'OnePlus',
                'price': Decimal('799.99'),
                'stock': 30,
            },
            # Tablets
            {
                'title': 'iPad Pro 12.9" (2024)',
                'category_slug': 'tablets',
                'description': 'iPad Pro 12.9 inches with M4 chip, 256GB storage. Ideal for creative work.',
                'brand': 'Apple',
                'price': Decimal('1099.99'),
                'stock': 18,
            },
            {
                'title': 'Samsung Galaxy Tab S9 Ultra',
                'category_slug': 'tablets',
                'description': 'Samsung Galaxy Tab S9 Ultra with Snapdragon 8 Gen 2, 12GB RAM, 256GB storage.',
                'brand': 'Samsung',
                'price': Decimal('1199.99'),
                'stock': 15,
            },
            {
                'title': 'iPad Air 11"',
                'category_slug': 'tablets',
                'description': 'iPad Air 11 inches with M2 chip, 256GB storage. Affordable creative tablet.',
                'brand': 'Apple',
                'price': Decimal('799.99'),
                'stock': 22,
            },
            # Accessories
            {
                'title': 'Apple AirPods Pro 2',
                'category_slug': 'accessories',
                'description': 'Apple AirPods Pro with Active Noise Cancellation and Adaptive Audio.',
                'brand': 'Apple',
                'price': Decimal('249.99'),
                'stock': 50,
            },
            {
                'title': 'USB-C Charging Cable',
                'category_slug': 'accessories',
                'description': 'High-quality USB-C charging cable, 2 meters long, supports fast charging.',
                'brand': 'Generic',
                'price': Decimal('19.99'),
                'stock': 100,
            },
            # Audio
            {
                'title': 'Sony WH-CH720N',
                'category_slug': 'audio',
                'description': 'Sony WH-CH720N Noise Cancelling Wireless Headphones. 35-hour battery life.',
                'brand': 'Sony',
                'price': Decimal('198.99'),
                'stock': 35,
            },
            {
                'title': 'Bose QuietComfort 45',
                'category_slug': 'audio',
                'description': 'Bose QuietComfort 45 headphones with world-class noise cancellation.',
                'brand': 'Bose',
                'price': Decimal('379.99'),
                'stock': 20,
            },
        ]

        category_map = {cat.slug: cat for cat in subcategories}

        products = []
        for data in products_data:
            category = category_map.get(data['category_slug'])
            if not category:
                continue

            product, created = Product.objects.get_or_create(
                title=data['title'],
                category=category,
                defaults={
                    'description': data['description'],
                    'brand': data['brand'],
                    'price': data['price'],
                    'stock_quantity': data['stock'],
                    'currency': 'USD',
                    'is_active': True,
                }
            )
            products.append(product)

        return products

    @staticmethod
    def _create_reviews(products, users):
        """Create reviews for products."""
        review_templates = {
            5: [
                "Excellent product! Exactly what I needed.",
                "Outstanding quality and fast shipping. Highly recommended!",
                "Best purchase I've made. Very happy with it.",
                "Amazing product, works perfectly. Worth every penny!",
                "Fantastic experience. Product is top-notch.",
            ],
            4: [
                "Very good product. Minor issues but overall satisfied.",
                "Great quality. Would buy again.",
                "Good value for money. Meets expectations.",
                "Solid product. Performs as advertised.",
                "Nice item. A bit pricey but good quality.",
            ],
            3: [
                "Average product. Does what it's supposed to.",
                "It's okay. Nothing special but decent.",
                "Acceptable quality. Some room for improvement.",
                "Fair product. Not great, not terrible.",
                "Decent, but I've seen better alternatives.",
            ],
            2: [
                "Not satisfied with this purchase.",
                "Below expectations. Disappointed.",
                "Poor quality compared to the price.",
                "Had some issues. Not recommended.",
                "Okay, but there are better options.",
            ],
            1: [
                "Very disappointed. Not worth the money.",
                "Terrible product. Do not buy!",
                "Broke after one week. Very unhappy.",
                "Waste of money. Poor quality.",
                "Not as described. Returning it.",
            ],
        }

        review_count = 0
        for product in products:
            # Each product gets 8-15 reviews from random users
            num_reviews = random.randint(8, 15)
            selected_users = random.sample(users, min(num_reviews, len(users)))

            # Bias towards higher ratings (more satisfied customers)
            ratings = [5, 5, 5, 5, 4, 4, 4, 3, 3, 2, 1]
            
            for user in selected_users:
                # Don't create duplicate reviews
                if Review.objects.filter(product=product, user=user).exists():
                    continue

                rating = random.choice(ratings)
                review_text = random.choice(review_templates[rating])

                Review.objects.create(
                    product=product,
                    user=user,
                    rating=rating,
                    title=f'Rating {rating} stars',
                    text=review_text,
                    helpful_count=random.randint(0, 10),
                )
                review_count += 1

        return review_count
