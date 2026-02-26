"""
ProductEmbeddingSearchTool — semantic vector search over AIDocumentEmbedding.

Uses pgvector cosine distance to find the most relevant product documents.
"""
import logging
from typing import Dict, Any, List, Optional

from django.db.models import Q

from products.models import AIDocument, AIDocumentEmbedding
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
    source_type: str = "product",
) -> Dict[str, Any]:
    """
    Semantic search over product document embeddings.

    Returns:
        {
            "tool": "ProductEmbeddingSearchTool",
            "count": int,
            "results": [{ document_id, source_id, score, text_content, metadata }]
        }
    """
    try:
        ai = _get_ai_service()
        query_embedding = ai.generate_embedding(query)

        if not query_embedding or all(v == 0.0 for v in query_embedding):
            return {
                "tool": "ProductEmbeddingSearchTool",
                "error": "Failed to generate query embedding",
                "count": 0,
                "results": [],
            }

        # pgvector cosine distance ordering
        from pgvector.django import CosineDistance

        qs = (
            AIDocumentEmbedding.objects
            .filter(document__source_type=source_type)
            .exclude(embedding__isnull=True)
            .annotate(distance=CosineDistance("embedding", query_embedding))
            .order_by("distance")[:top_k]
        )

        results = []
        for emb in qs.select_related("document"):
            doc = emb.document
            results.append({
                "document_id": str(doc.id),
                "source_id": doc.source_id,
                "source_type": doc.source_type,
                "score": round(1 - emb.distance, 4),  # cosine similarity
                "text_content": doc.text_content,
                "metadata": doc.metadata_json,
            })

        return {
            "tool": "ProductEmbeddingSearchTool",
            "count": len(results),
            "results": results,
        }
    except Exception as e:
        logger.exception("ProductEmbeddingSearchTool error")
        return {"tool": "ProductEmbeddingSearchTool", "error": str(e), "count": 0, "results": []}
