"""
Hybrid Search — fuse BM25 keyword results with vector similarity results.

Implements: FinalScore = α × VectorSimilarity + β × BM25Score
with min-max normalization on raw scores before fusion.
"""
from typing import List, Dict, Any, Optional
from ai_agentic_rag.config import HYBRID_ALPHA, HYBRID_BETA


def _normalize(scores: List[float]) -> List[float]:
    """Min-max normalize a list of scores to [0, 1]."""
    if not scores:
        return []
    mn, mx = min(scores), max(scores)
    rng = mx - mn
    if rng == 0:
        return [1.0] * len(scores)
    return [(s - mn) / rng for s in scores]


def fuse_results(
    *,
    vector_results: List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    top_k: int = 10,
    alpha: Optional[float] = None,
    beta: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Merge and re-rank results from vector and BM25 retrieval.

    Each result dict is expected to have at least:
      - source_id  (product UUID)
      - score / rank  (higher = better)
      - text_content
      - metadata

    Returns dict with "results", "alpha", "beta".
    """
    a = alpha if alpha is not None else HYBRID_ALPHA
    b = beta if beta is not None else HYBRID_BETA

    # Collect all unique source_ids → bucket
    bucket: Dict[str, Dict[str, Any]] = {}

    # ── Vector scores ──────────────────────────────────
    v_scores = [r.get("score", 0.0) for r in vector_results]
    v_norm = _normalize(v_scores)

    for idx, r in enumerate(vector_results):
        sid = r["source_id"]
        bucket.setdefault(sid, {
            "source_id": sid,
            "text_content": r.get("text_content", ""),
            "metadata": r.get("metadata", {}),
            "vector_score": 0.0,
            "bm25_score": 0.0,
        })
        bucket[sid]["vector_score"] = v_norm[idx] if idx < len(v_norm) else 0.0

    # ── BM25 scores ────────────────────────────────────
    b_scores = [r.get("rank", 0.0) for r in bm25_results]
    b_norm = _normalize(b_scores)

    for idx, r in enumerate(bm25_results):
        sid = r["source_id"]
        bucket.setdefault(sid, {
            "source_id": sid,
            "text_content": r.get("text_content", ""),
            "metadata": r.get("metadata", {}),
            "vector_score": 0.0,
            "bm25_score": 0.0,
        })
        bucket[sid]["bm25_score"] = b_norm[idx] if idx < len(b_norm) else 0.0

    # ── Fuse ───────────────────────────────────────────
    for entry in bucket.values():
        entry["final_score"] = round(
            a * entry["vector_score"] + b * entry["bm25_score"], 4
        )

    ranked = sorted(bucket.values(), key=lambda x: x["final_score"], reverse=True)[:top_k]

    return {
        "alpha": a,
        "beta": b,
        "results": ranked,
    }
