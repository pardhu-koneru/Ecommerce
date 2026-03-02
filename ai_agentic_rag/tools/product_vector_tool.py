"""
ProductEmbeddingSearchTool — semantic vector search over AIDocumentEmbedding.

Uses pgvector cosine distance to find the most relevant product documents.
Includes a per-request embedding cache to avoid redundant Ollama calls
(e.g., HybridSearchFusionTool + standalone vector search on the same query).
"""
import logging
import threading
from typing import Dict, Any, List, Optional

from django.db.models import Q

from products.models import AIDocument, AIDocumentEmbedding
from products.ai_service import AIService
from ai_agentic_rag.config import VECTOR_TOP_K

logger = logging.getLogger(__name__)

_ai_service: Optional[AIService] = None
# Thread-safe per-request embedding cache (cleared between requests)
_embedding_cache: Dict[str, List[float]] = {}
_cache_lock = threading.Lock()


def _get_ai_service() -> AIService:
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service


def clear_embedding_cache():
    """Call at the start of each RAG request to reset the cache."""
    global _embedding_cache
    with _cache_lock:
        _embedding_cache = {}


def _get_or_create_embedding(query: str) -> List[float]:
    """
    Return a cached embedding for the query text, or generate & cache a new one.
    Avoids redundant Ollama calls when the same query is embedded multiple times
    within a single request (e.g., HybridSearchFusionTool + standalone vector search).
    """
    with _cache_lock:
        if query in _embedding_cache:
            logger.debug(f"Embedding cache HIT for query: {query[:60]}...")
            return _embedding_cache[query]

    ai = _get_ai_service()
    embedding = ai.generate_embedding(query)

    with _cache_lock:
        _embedding_cache[query] = embedding

    return embedding


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
        query_embedding = _get_or_create_embedding(query)

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
