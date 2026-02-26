"""
Ranking utilities — re-rank and score product candidates
using signals from multiple retrieval sources.
"""
from typing import List, Dict, Any


def reciprocal_rank_fusion(
    result_lists: List[List[Dict[str, Any]]],
    k: int = 60,
    top_n: int = 10,
) -> List[Dict[str, Any]]:
    """
    Reciprocal Rank Fusion (RRF) across multiple ranked lists.

    RRFScore(d) = Σ 1 / (k + rank_i(d))

    Args:
        result_lists: list of ranked result lists (each result has "source_id")
        k: smoothing constant (default 60)
        top_n: number of results to return

    Returns:
        Fused list sorted by RRF score descending.
    """
    scores: Dict[str, float] = {}
    data: Dict[str, Dict[str, Any]] = {}

    for rlist in result_lists:
        for rank, item in enumerate(rlist, start=1):
            sid = item.get("source_id") or item.get("id", "")
            scores[sid] = scores.get(sid, 0.0) + 1.0 / (k + rank)
            if sid not in data:
                data[sid] = item

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]

    results = []
    for sid, score in ranked:
        entry = dict(data.get(sid, {}))
        entry["rrf_score"] = round(score, 6)
        results.append(entry)

    return results


def boost_by_rating(
    results: List[Dict[str, Any]],
    rating_key: str = "rating_avg",
    boost_weight: float = 0.1,
) -> List[Dict[str, Any]]:
    """
    Lightly boost results by product rating.

    new_score = current_score + boost_weight × (rating / 5.0)
    """
    for r in results:
        rating = r.get("metadata", {}).get(rating_key, 0)
        if not rating:
            rating = r.get(rating_key, 0)
        current = r.get("final_score", r.get("rrf_score", r.get("score", 0)))
        r["boosted_score"] = round(current + boost_weight * (float(rating) / 5.0), 4)

    return sorted(results, key=lambda x: x.get("boosted_score", 0), reverse=True)
