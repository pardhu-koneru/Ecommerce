"""
Context Builder — assembles tool outputs into a structured context string
that the Generator LLM reads to produce the final answer.

Deduplicates products, prioritises high-scoring results, and formats
the context with clear section headers so the LLM can ground its answer.

IMPORTANT: For products retrieved via embedding/BM25/hybrid search, the
AIDocument text_content (which contains the full synthesized description,
vision analysis, and specifications) is included directly in the context.
This is the primary data the LLM should read — per the AIDocument design.
"""
import logging
from typing import Dict, Any, List

from ai_agentic_rag.state import AgentState

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 14_000  # Safety cap to stay within LLM context window
MAX_TEXT_CONTENT_PER_PRODUCT = 1200  # Truncate individual product text to stay within budget


def _dedup_products(items: List[Dict[str, Any]], id_key: str = "source_id") -> List[Dict[str, Any]]:
    """Remove duplicates by source_id / id, keeping first occurrence."""
    seen = set()
    unique = []
    for item in items:
        pid = item.get(id_key) or item.get("id") or item.get("product_id", "")
        if pid and pid in seen:
            continue
        seen.add(pid)
        unique.append(item)
    return unique


def _format_retrieved_product(p: Dict[str, Any]) -> str:
    """
    Format a product result from embedding/BM25/hybrid tools.

    Uses text_content (the curated AIDocument text with vision analysis,
    description, and full specifications) as the primary data source.
    Falls back to metadata-based formatting if text_content is absent.
    """
    text_content = p.get("text_content", "")
    meta = p.get("metadata", {})

    if text_content:
        # Use the curated AI document text directly — it includes
        # vision analysis, product info, description, and all specs
        truncated = text_content.strip()
        if len(truncated) > MAX_TEXT_CONTENT_PER_PRODUCT:
            truncated = truncated[:MAX_TEXT_CONTENT_PER_PRODUCT] + "..."

        lines = [truncated]

        # Append relevance score
        for score_key in ("final_score", "score", "boosted_score", "rank", "rrf_score"):
            if p.get(score_key) is not None:
                lines.append(f"RELEVANCE SCORE: {p[score_key]}")
                break

        return "\n".join(lines)

    # Fallback: format from metadata fields (for results without text_content)
    return _format_structured_product({**meta, **p})


def _format_structured_product(p: Dict[str, Any]) -> str:
    """
    Format a product from structured data (SQL/stock/comparison results).
    Handles key name variations in metadata vs direct product fields.
    """
    lines = []
    title = p.get("title") or p.get("product_title", "Unknown Product")
    lines.append(f"• {title}")

    if p.get("brand"):
        lines.append(f"  Brand: {p['brand']}")
    if p.get("category"):
        lines.append(f"  Category: {p['category']}")
    if p.get("price") is not None:
        currency = p.get("currency", "INR")
        lines.append(f"  Price: {currency} {p['price']}")

    # Handle rating key variations: rating_avg or rating
    rating = p.get("rating_avg") if p.get("rating_avg") is not None else p.get("rating")
    rating_count = p.get("rating_count", 0)
    if rating is not None:
        lines.append(f"  Rating: {rating}/5 ({rating_count} reviews)")

    # Handle stock key variations: stock_quantity or in_stock
    if p.get("stock_quantity") is not None:
        stock = "In Stock" if p["stock_quantity"] > 0 else "Out of Stock"
        lines.append(f"  Stock: {stock} ({p['stock_quantity']} units)")
    elif p.get("in_stock") is not None:
        lines.append(f"  Stock: {'In Stock' if p['in_stock'] else 'Out of Stock'}")

    # Attributes / Specifications
    attrs = p.get("attributes", {})
    if isinstance(attrs, dict) and attrs:
        lines.append("  Specifications:")
        for k, v in list(attrs.items())[:15]:
            lines.append(f"    - {k}: {v}")
    elif isinstance(attrs, list):
        lines.append("  Specifications:")
        for attr in attrs[:15]:
            if isinstance(attr, dict):
                lines.append(f"    - {attr.get('key', '')}: {attr.get('value', '')}")

    # Score info
    for score_key in ("final_score", "score", "boosted_score", "rank", "rrf_score"):
        if p.get(score_key) is not None:
            lines.append(f"  Relevance: {p[score_key]}")
            break

    return "\n".join(lines)


def _format_review(r: Dict[str, Any]) -> str:
    """Format a review summary item."""
    title = r.get("product_title", "")
    summary = r.get("summary", r.get("text_content", ""))
    avg = r.get("avg_rating", "?")
    count = r.get("review_count", "?")
    return f"• {title} — avg {avg}/5, {count} reviews\n  Summary: {summary[:500]}"


def build_context(state: AgentState) -> AgentState:
    """
    LangGraph node: build the context string from tool_outputs.
    Updates state["context"].

    For retrieved products (embedding/BM25/hybrid), the full AIDocument
    text_content is included — this contains synthesized descriptions,
    vision analysis, and complete specifications.
    For SQL/stock results, structured metadata formatting is used.
    """
    tool_outputs = state.get("tool_outputs", [])
    analysis = state.get("analysis", {})
    query = state.get("query", "")

    sections: List[str] = []
    sections.append(f"USER QUERY: {query}")
    sections.append(f"INTENT: {analysis.get('intent', 'unknown')}")
    sections.append("")

    # Categorise tool outputs
    product_results: List[Dict[str, Any]] = []
    review_results: List[Dict[str, Any]] = []
    stock_results: List[Dict[str, Any]] = []
    comparison_results: List[Dict[str, Any]] = []
    image_desc = ""

    for to in tool_outputs:
        tool = to.get("tool", "")
        result = to.get("result", {})

        if tool in ("ProductEmbeddingSearchTool", "BM25KeywordSearchTool", "HybridSearchFusionTool"):
            product_results.extend(result.get("results", []))
        elif tool == "ReviewEmbeddingSearchTool":
            review_results.extend(result.get("results", []))
        elif tool in ("StockCheckTool", "SQLFilterTool"):
            stock_results.extend(result.get("products", []))
        elif tool == "ComparisonTool":
            comparison_results.extend(result.get("products", []))
        elif tool == "ImageEmbeddingSearchTool":
            product_results.extend(result.get("results", []))
            image_desc = result.get("image_description", "")

    # ── Product section (retrieved via embedding/BM25/hybrid) ──
    # Uses full text_content with specs, descriptions, vision analysis
    if product_results:
        unique = _dedup_products(product_results)[:8]
        sections.append("=== RETRIEVED PRODUCTS (with full specifications) ===")
        for i, p in enumerate(unique, 1):
            sections.append(f"--- Product {i} ---")
            sections.append(_format_retrieved_product(p))
            sections.append("")

    # ── SQL / Stock section (structured data) ──────────
    if stock_results:
        unique = _dedup_products(stock_results, id_key="id")[:8]
        sections.append("=== PRODUCT DATA (SQL) ===")
        for p in unique:
            sections.append(_format_structured_product(p))
        sections.append("")

    # ── Review section ─────────────────────────────────
    if review_results:
        sections.append("=== REVIEWS ===")
        for r in review_results[:5]:
            sections.append(_format_review(r))
        sections.append("")

    # ── Comparison section ─────────────────────────────
    if comparison_results:
        sections.append("=== COMPARISON ===")
        for p in comparison_results:
            sections.append(_format_structured_product(p))
        sections.append("")

    # ── Image description ──────────────────────────────
    if image_desc:
        sections.append(f"=== IMAGE ANALYSIS ===\n{image_desc}\n")

    context = "\n".join(sections)

    # Truncate if too long
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n... [truncated]"

    state["context"] = context
    logger.info(f"ContextBuilder → {len(context)} chars")
    return state
