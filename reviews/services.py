"""
Business logic services for reviews module.
Handles review operations, statistics, and AI-related functionality.
"""
import logging
from django.db.models import Avg, Count, Q
from django.utils import timezone
from .models import Review, ReviewEmbedding
from products.models import Product

logger = logging.getLogger(__name__)


class ReviewService:
    """
    Service layer for review-related operations.
    """
    
    @staticmethod
    def get_product_review_stats(product_id: str) -> dict:
        """
        Get comprehensive review statistics for a product.
        
        Returns:
        {
            'total_reviews': int,
            'avg_rating': float,
            'rating_distribution': {1: count, 2: count, ...},
            'recent_reviews': [Review objects],
            'summary': str or None
        }
        """
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return None
        
        reviews = Review.objects.filter(product=product)
        
        stats = reviews.aggregate(
            total_reviews=Count('id'),
            avg_rating=Avg('rating')
        )
        
        # Distribution by rating
        rating_dist = {}
        for i in range(1, 6):
            rating_dist[i] = reviews.filter(rating=i).count()
        
        # AI summary if available
        summary = None
        try:
            embedding = ReviewEmbedding.objects.get(product=product)
            summary = embedding.summary
        except ReviewEmbedding.DoesNotExist:
            pass
        
        return {
            'total_reviews': stats['total_reviews'],
            'avg_rating': stats['avg_rating'] or 0.0,
            'rating_distribution': rating_dist,
            'summary': summary,
        }
    
    @staticmethod
    def search_helpful_reviews(product_id: str, query: str) -> list:
        """
        Search reviews and rank by helpfulness and relevance.
        
        Strategy:
        - Keyword match in title/text
        - Sort by helpful_count (descending)
        - Then by rating diversity (high and low ratings shown first)
        
        Args:
            product_id: Product UUID
            query: Search query string
            
        Returns:
            List of Review objects
        """
        reviews = Review.objects.filter(
            Q(product_id=product_id) & (Q(title__icontains=query) | Q(text__icontains=query))
        ).order_by('-helpful_count', '-rating')
        
        return list(reviews)
    
    @staticmethod
    def get_reviews_needing_embedding_update() -> list:
        """
        Get list of products whose review embeddings are outdated.
        
        A ReviewEmbedding is outdated if:
        - There are 5+ new reviews since last generation
        - is_outdated flag is True
        
        Returns:
            List of product IDs
        """
        outdated = ReviewEmbedding.objects.filter(is_outdated=True).values_list('product_id', flat=True)
        return list(outdated)
    
    @staticmethod
    def mark_embedding_outdated(product_id: str):
        """Mark a product's review embedding as needing regeneration."""
        try:
            embedding = ReviewEmbedding.objects.get(product_id=product_id)
            embedding.is_outdated = True
            embedding.save()
            logger.info(f"Marked ReviewEmbedding as outdated for product {product_id}")
        except ReviewEmbedding.DoesNotExist:
            logger.warning(f"ReviewEmbedding not found for product {product_id}")


class ReviewRAGService:
    """
    Service for using reviews in Retrieval Augmented Generation (RAG).
    
    Enables semantic search across review summaries to answer questions like:
    - "Does this laptop overheat while gaming?"
    - "How is the battery life in real-world usage?"
    """
    
    @staticmethod
    def search_reviews_for_question(question: str, product_id: str = None) -> list:
        """
        Search review embeddings for answers to a question.
        
        Flow:
        1. Generate embedding vector from the question
        2. Search ReviewEmbedding vectors using pgvector similarity
        3. Return matching review summaries with metadata
        
        Args:
            question: Natural language question
            product_id: Optional product ID to search within
            
        Returns:
            List of matching review embeddings with similarity scores
        """
        from products.ai_service import AIService
        
        try:
            ai_service = AIService()
            
            # Generate embedding for the question
            question_embedding = ai_service.generate_embedding(question)
            
            # Query review embeddings by similarity
            # This requires pgvector <-> operator
            embeddings = ReviewEmbedding.objects.all()
            
            if product_id:
                embeddings = embeddings.filter(product_id=product_id)
            
            # Sort by similarity (would use pgvector distance in production)
            # For now, just return sorted by relevance score
            results = []
            for embedding in embeddings:
                if embedding.embedding:
                    # Calculate cosine similarity
                    similarity = cosine_similarity(question_embedding, embedding.embedding)
                    results.append({
                        'embedding': embedding,
                        'similarity': similarity,
                        'product_id': str(embedding.product_id),
                        'summary': embedding.summary,
                        'review_count': embedding.review_count,
                        'avg_rating': embedding.avg_rating,
                    })
            
            # Sort by similarity
            results.sort(key=lambda x: x['similarity'], reverse=True)
            
            logger.info(f"Found {len(results)} matching review embeddings for question")
            return results
        
        except Exception as e:
            logger.error(f"Error searching review embeddings: {e}")
            return []
    
    @staticmethod
    def get_ai_answer_to_review_question(question: str, product_id: str = None) -> str:
        """
        Use LLM to generate an answer based on review summaries.
        
        This is the main entry point for answering customer questions
        using the review embedding data.
        
        Example questions:
        - "Does this laptop overheat while gaming?"
        - "How is the battery life in real-world usage?"
        - "Is this product durable?"
        
        Args:
            question: Customer question
            product_id: Optional product ID to search
            
        Returns:
            AI-generated answer based on review summaries
        """
        from groq import Groq
        import os
        
        # Search for relevant review summaries
        relevant_reviews = ReviewRAGService.search_reviews_for_question(question, product_id)
        
        if not relevant_reviews:
            return "I don't have enough review data to answer this question yet."
        
        # Build context from review summaries
        context = "Review Summaries:\n\n"
        for i, result in enumerate(relevant_reviews[:3], 1):  # Top 3 results
            context += (
                f"{i}. Product: {result['embedding'].product.title}\n"
                f"   Reviews: {result['review_count']} (Avg Rating: {result['avg_rating']:.1f}/5)\n"
                f"   Summary: {result['summary'][:500]}...\n\n"
            )
        
        try:
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            
            prompt = f"""
Based on the following customer review summaries, please answer the user's question:

Question: {question}

{context}

Provide a helpful, concise answer (2-3 sentences) that directly addresses the customer's question based on what other customers have said. If the reviews don't contain information about the specific topic, say so.
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
                max_completion_tokens=300,
                top_p=0.9,
            )
            
            answer = completion.choices[0].message.content
            logger.info("Generated AI answer from review summaries")
            return answer
        
        except Exception as e:
            logger.error(f"Error generating AI answer: {e}")
            return "Unable to generate an answer at this time."


def cosine_similarity(vec1: list, vec2: list) -> float:
    """
    Calculate cosine similarity between two vectors.
    
    Returns similarity score between -1 and 1 (typically 0 to 1 for embeddings).
    """
    if not vec1 or not vec2:
        return 0.0
    
    import math
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)
