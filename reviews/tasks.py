"""
Celery tasks for asynchronous review processing.
Handles review embedding generation, sentiment analysis, and summarization.
"""
from celery import shared_task
import logging
import json
from django.utils import timezone
from datetime import datetime

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def check_and_regenerate_review_embedding(self, product_id: str):
    """
    Check if a product has reached 5 new reviews since last embedding update.
    If so, regenerate the review embedding.
    
    Triggered after every new/updated review.
    
    Logic:
    1. Check if ReviewEmbedding exists for this product
    2. If not, create one (even if < 5 reviews)
    3. Count reviews since last update
    4. If >= 5 new reviews, trigger regeneration
    
    Args:
        product_id: UUID of product
        
    Returns:
        Dict with regeneration status
    """
    from products.models import Product
    from reviews.models import Review, ReviewEmbedding
    
    try:
        logger.info(f"[Review Task] Checking embedding for product: {product_id}")
        
        # Get product
        product = Product.objects.get(id=product_id)
        logger.info(f"Product found: {product.title}")
        
        # Get or create ReviewEmbedding
        embedding, created = ReviewEmbedding.objects.get_or_create(product=product)
        
        if created:
            logger.info(f"Created new ReviewEmbedding for {product.title}")
            # Trigger initial generation for all existing reviews
            return generate_review_embedding.delay(product_id)
        
        # Count total reviews
        total_reviews = Review.objects.filter(product=product).count()
        reviews_since_update = total_reviews - embedding.review_count
        
        logger.info(
            f"Product: {product.title} | "
            f"Total reviews: {total_reviews} | "
            f"Since last update: {reviews_since_update} | "
            f"Is outdated: {embedding.is_outdated}"
        )
        
        # Regenerate if 5+ new reviews or marked as outdated
        if reviews_since_update >= 5 or embedding.is_outdated:
            logger.info(f"Triggering embedding regeneration ({reviews_since_update} new reviews)")
            return generate_review_embedding.delay(product_id)
        else:
            logger.info(f"Not enough reviews yet ({reviews_since_update}/5)")
            return {"status": "no_regeneration_needed", "reviews_since_update": reviews_since_update}
    
    except Product.DoesNotExist:
        logger.error(f"Product not found: {product_id}")
        return {"status": "error", "message": "Product not found"}
    except Exception as e:
        logger.error(f"Error checking review embedding: {e}")
        self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3)
def generate_review_embedding(self, product_id: str):
    """
    Generate AI embedding and summary for product reviews.
    
    Flow:
    1. Get all reviews for product
    2. Generate summary using LLM
    3. Generate embedding vector from summary
    4. Perform sentiment analysis
    5. Create/update ReviewEmbedding with metadata
    6. Update AIDocument for RAG (linked to reviews)
    
    Args:
        product_id: UUID of product
        
    Returns:
        Dict with embedding status and metadata
    """
    from products.models import Product, AIDocument
    from reviews.models import Review, ReviewEmbedding
    from products.ai_service import AIService
    
    try:
        logger.info(f"[Review Embedding] Generating for product: {product_id}")
        
        product = Product.objects.get(id=product_id)
        reviews = Review.objects.filter(product=product).order_by('-created_at')
        total_reviews = reviews.count()
        
        if total_reviews == 0:
            logger.info(f"No reviews for product {product.title}")
            return {"status": "no_reviews", "product_id": product_id}
        
        # Calculate review statistics
        avg_rating = sum(r.rating for r in reviews) / total_reviews if total_reviews else 0
        rating_distribution = {}
        for i in range(1, 6):
            rating_distribution[str(i)] = reviews.filter(rating=i).count()
        
        logger.info(f"Product: {product.title} | Reviews: {total_reviews} | Avg Rating: {avg_rating:.2f}")
        
        # Get AI service (handles vision + embeddings)
        ai_service = AIService()
        
        # Generate summary from reviews
        summary_text = generate_review_summary(reviews, product)
        logger.info(f"Generated summary ({len(summary_text)} chars)")
        
        # Generate embedding from summary
        embedding_vector = ai_service.generate_embedding(summary_text)
        logger.info(f"Generated embedding ({len(embedding_vector)} dimensions)")
        
        # Analyze sentiment
        sentiment = analyze_review_sentiment(reviews)
        logger.info(f"Sentiment: {sentiment}")
        
        # Build comprehensive metadata
        metadata = {
            "type": "review_summary",
            "review_count": total_reviews,
            "avg_rating": round(avg_rating, 2),
            "sentiment": sentiment,
            "last_updated_at": timezone.now().isoformat(),
            "product_id": str(product.id),
            "product_title": product.title,
            "category": product.category.name,
            "rating_distribution": rating_distribution,
            "price": float(product.price),
            "currency": product.currency,
            "embedding_model": ai_service.embedding_model,
            "embedding_dimension": ai_service.embedding_dim,
        }
        
        # Update or create ReviewEmbedding
        embedding_obj, created = ReviewEmbedding.objects.update_or_create(
            product=product,
            defaults={
                'summary': summary_text,
                'embedding': embedding_vector,
                'review_count': total_reviews,
                'avg_rating': avg_rating,
                'is_outdated': False,
                'metadata_json': metadata
            }
        )
        
        logger.info(f"ReviewEmbedding {'created' if created else 'updated'} for {product.title}")
        
        # Also create/update AIDocument for this review summary (for RAG)
        # This allows the LLM to search across review summaries
        ai_doc_metadata = {
            'product_id': str(product.id),
            'product_title': product.title,
            'category': product.category.name,
            'review_count': total_reviews,
            'avg_rating': round(avg_rating, 2),
            'sentiment': sentiment,
            'generated_by': 'ReviewEmbeddingService',
            'version': 1,
        }
        
        AIDocument.objects.update_or_create(
            source_type='review',
            source_id=str(product.id),
            defaults={
                'text_content': summary_text,
                'metadata_json': ai_doc_metadata,
                'is_indexed': True
            }
        )
        
        logger.info(f"AIDocument created/updated for reviews of {product.title}")
        
        return {
            "status": "success",
            "product_id": product_id,
            "total_reviews": total_reviews,
            "avg_rating": avg_rating,
            "sentiment": sentiment,
            "summary_length": len(summary_text),
            "embedding_dimension": len(embedding_vector),
        }
    
    except Product.DoesNotExist:
        logger.error(f"Product not found")
        return {"status": "error", "message": "Product not found"}
    except Exception as e:
        logger.error(f"Error generating review embedding: {e}", exc_info=True)
        self.retry(exc=e, countdown=60)


def generate_review_summary(reviews, product) -> str:
    """
    Generate AI summary from reviews using LLM.
    
    Summarizes key themes, pros/cons, and common concerns from reviews.
    Designed to answer: "What do customers say about this product?"
    
    Args:
        reviews: QuerySet of Review objects
        product: Product object
        
    Returns:
        Summary text
    """
    from products.llm_service import get_image_base64, get_image_media_type
    from groq import Groq
    import os
    
    if not reviews.exists():
        return "No reviews available yet."
    
    # Get recent reviews (last 20) for summary
    recent_reviews = reviews[:20]
    
    # Build review compilation
    review_compilation = "Customer Reviews:\n\n"
    for idx, review in enumerate(recent_reviews, 1):
        review_compilation += (
            f"{idx}. Rating: {review.rating}★\n"
            f"   Title: {review.title}\n"
            f"   Review: {review.text}\n\n"
        )
    
    # Use LLM to generate summary
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        
        prompt = f"""
You are an expert product review analyst. Analyze the following customer reviews for '{product.title}' and generate a concise summary that covers:

1. Common positive themes and frequently praised features
2. Common criticisms or concerns
3. Specific use cases where customers report success or problems
4. Answer to key questions like: "How is the battery life?", "Does it overheat?", "Is it durable?", etc.
5. Overall sentiment and recommendation level

Reviews to analyze:
{review_compilation}

Generate a comprehensive but concise summary (300-400 words) that would help a potential buyer understand what customers actually experience with this product. Be specific with examples from the reviews.
"""
        
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.5,
            max_completion_tokens=500,
            top_p=0.9,
        )
        
        summary = completion.choices[0].message.content
        logger.info("Generated review summary via Groq LLM")
        return summary
    
    except Exception as e:
        logger.error(f"Error generating LLM summary: {e}")
        # Fallback: create basic summary
        return generate_basic_summary(reviews, product)


def generate_basic_summary(reviews, product) -> str:
    """
    Fallback summary generation if LLM is unavailable.
    """
    from django.db.models import Avg
    
    stats = reviews.aggregate(
        total=models.Count('id'),
        avg_rating=Avg('rating')
    )
    
    # Get pros and cons by analyzing ratings
    high_rated = reviews.filter(rating__gte=4)
    low_rated = reviews.filter(rating__lte=2)
    
    summary = f"""
Summary of {product.title} Reviews:

Total Reviews: {stats['total']}
Average Rating: {stats['avg_rating']:.1f}/5

Positive Feedback:
{generate_theme_summary(high_rated)}

Areas of Concern:
{generate_theme_summary(low_rated)}

This {'appears to be well-reviewed' if stats['avg_rating'] >= 4 else 'has mixed reviews' if stats['avg_rating'] >= 3 else 'is not highly recommended'} by customers.
"""
    
    return summary.strip()


def generate_theme_summary(reviews_subset) -> str:
    """Extract common themes from a set of reviews."""
    if not reviews_subset.exists():
        return "No significant feedback in this category."
    
    # Simple approach: show most recent reviews' titles
    titles = [r.title for r in reviews_subset[:3]]
    return "\n".join(f"- {title}" for title in titles if title)


def analyze_review_sentiment(reviews) -> str:
    """
    Determine overall sentiment based on rating distribution.
    
    Returns sentiment string: "very_negative", "negative", "neutral", "positive", "very_positive"
    """
    from django.db.models import Avg
    
    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
    
    if avg_rating < 2:
        return "very_negative"
    elif avg_rating < 3:
        return "negative"
    elif avg_rating < 3.5:
        return "neutral"
    elif avg_rating < 4.5:
        return "positive"
    else:
        return "very_positive"


# Import Django models at bottom to avoid circular imports
from django.db import models
