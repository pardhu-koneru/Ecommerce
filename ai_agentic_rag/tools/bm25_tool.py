"""
BM25KeywordSearchTool — exact keyword matching via PostgreSQL full-text search.

Triggered when the query contains model numbers, exact specs, SKU patterns,
or brand constraints that require keyword precision.
"""
import logging
from typing import Dict, Any, Optional

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

from products.models import AIDocument
from ai_agentic_rag.config import BM25_TOP_K

logger = logging.getLogger(__name__)


def run(
    *,
    query: str,
    top_k: int = BM25_TOP_K,
    source_type: str = "product",
) -> Dict[str, Any]:
    """
    Full-text (BM25-style) keyword search over AIDocument.text_content.

    Uses PostgreSQL ts_vector + ts_rank for ranked keyword matching.

    Returns:
        {
            "tool": "BM25KeywordSearchTool",
            "count": int,
            "results": [{ document_id, source_id, rank, text_content, metadata }]
        }
    """
    try:
        search_vector = SearchVector("text_content")
        search_query = SearchQuery(query, search_type="websearch")

        qs = (
            AIDocument.objects
            .filter(source_type=source_type, is_indexed=True)
            .annotate(
                search=search_vector,
                rank=SearchRank(search_vector, search_query),
            )
            .filter(search=search_query)
            .order_by("-rank")[:top_k]
        )

        results = []
        for doc in qs:
            results.append({
                "document_id": str(doc.id),
                "source_id": doc.source_id,
                "source_type": doc.source_type,
                "rank": round(float(doc.rank), 4),
                "text_content": doc.text_content,
                "metadata": doc.metadata_json,
            })

        return {
            "tool": "BM25KeywordSearchTool",
            "count": len(results),
            "results": results,
        }
    except Exception as e:
        logger.exception("BM25KeywordSearchTool error")
        return {"tool": "BM25KeywordSearchTool", "error": str(e), "count": 0, "results": []}
