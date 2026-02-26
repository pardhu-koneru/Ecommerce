"""
ReviewEmbeddingSearchTool — semantic vector search over ReviewEmbedding.

Retrieves review summaries that are semantically similar to the query.
Uses pgvector cosine distance on the 768-dim review summary embeddings.
"""
import logging
from typing import Dict, Any, Optional

from reviews.models import ReviewEmbedding
from products.ai_service import AIService
from ai_agentic_rag.config import VECTOR_TOP_K

logger = logging.getLogger(__name__)

_ai_service: Optional[AIService] = None


def _get_ai_service() -> AIService:
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service


def run(
    *,
    query: str,
    top_k: int = VECTOR_TOP_K,
    min_rating: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Semantic search over review summary embeddings.

    Returns:
        {
            "tool": "ReviewEmbeddingSearchTool",
            "count": int,
            "results": [{ product_id, summary, score, review_count, avg_rating, metadata }]
        }
    """
    try:
        ai = _get_ai_service()
        query_embedding = ai.generate_embedding(query)

        if not query_embedding or all(v == 0.0 for v in query_embedding):
            return {
                "tool": "ReviewEmbeddingSearchTool",
                "error": "Failed to generate query embedding",
                "count": 0,
                "results": [],
            }

        from pgvector.django import CosineDistance

        qs = (
            ReviewEmbedding.objects
            .exclude(embedding__isnull=True)
            .annotate(distance=CosineDistance("embedding", query_embedding))
        )

        if min_rating is not None:
            qs = qs.filter(avg_rating__gte=min_rating)

        qs = qs.order_by("distance")[:top_k]

        results = []
        for re in qs.select_related("product"):
            results.append({
                "product_id": str(re.product_id),
                "product_title": re.product.title,
                "summary": re.summary,
                "score": round(1 - re.distance, 4),
                "review_count": re.review_count,
                "avg_rating": re.avg_rating,
                "metadata": re.metadata_json,
            })

        return {
            "tool": "ReviewEmbeddingSearchTool",
            "count": len(results),
            "results": results,
        }
    except Exception as e:
        logger.exception("ReviewEmbeddingSearchTool error")
        return {"tool": "ReviewEmbeddingSearchTool", "error": str(e), "count": 0, "results": []}
