"""
HybridSearchFusionTool — combined BM25 + vector scoring.

Runs both BM25KeywordSearchTool and ProductEmbeddingSearchTool,
then fuses results using: FinalScore = α·VectorSimilarity + β·BM25Score
"""
import logging
from typing import Dict, Any, Optional

from ai_agentic_rag.tools import bm25_tool, product_vector_tool
from ai_agentic_rag.retrieval.hybrid_search import fuse_results
from ai_agentic_rag.config import HYBRID_TOP_K

logger = logging.getLogger(__name__)


def run(
    *,
    query: str,
    top_k: int = HYBRID_TOP_K,
    alpha: Optional[float] = None,
    beta: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Execute hybrid search: BM25 + vector, fused with weighted scoring.

    Returns:
        {
            "tool": "HybridSearchFusionTool",
            "count": int,
            "alpha": float,
            "beta": float,
            "results": [{ source_id, final_score, vector_score, bm25_score, text_content, metadata }]
        }
    """
    try:
        # Run both retrieval paths
        vector_results = product_vector_tool.run(query=query, top_k=top_k * 2)
        bm25_results = bm25_tool.run(query=query, top_k=top_k * 2)

        fused = fuse_results(
            vector_results=vector_results.get("results", []),
            bm25_results=bm25_results.get("results", []),
            top_k=top_k,
            alpha=alpha,
            beta=beta,
        )

        return {
            "tool": "HybridSearchFusionTool",
            "count": len(fused["results"]),
            "alpha": fused["alpha"],
            "beta": fused["beta"],
            "results": fused["results"],
        }
    except Exception as e:
        logger.exception("HybridSearchFusionTool error")
        return {"tool": "HybridSearchFusionTool", "error": str(e), "count": 0, "results": []}
