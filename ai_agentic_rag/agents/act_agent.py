"""
Act Agent (Tool Executor) — executes one plan step at a time.

Responsibilities:
  - Parse the current step description to identify the right tool
  - Extract parameters from query + analysis + prior tool outputs
  - Execute the tool and store structured output in state["tool_outputs"]
  - Advance state["current_step_index"]
"""
import json
import logging
import re
from typing import Dict, Any, Optional, List

from ai_agentic_rag.config import GROQ_API_KEY, LLM_MODEL
from ai_agentic_rag.state import AgentState
from ai_agentic_rag.tools import (
    sql_tool,
    product_vector_tool,
    review_vector_tool,
    image_vector_tool,
    bm25_tool,
    hybrid_fusion_tool,
    stock_tool,
    comparison_tool,
)

logger = logging.getLogger(__name__)

# ── Tool routing map (step keyword → tool module) ──────────────────

_TOOL_MAP = {
    "SQLFilterTool": sql_tool,
    "ProductEmbeddingSearchTool": product_vector_tool,
    "ReviewEmbeddingSearchTool": review_vector_tool,
    "ImageEmbeddingSearchTool": image_vector_tool,
    "BM25KeywordSearchTool": bm25_tool,
    "HybridSearchFusionTool": hybrid_fusion_tool,
    "StockCheckTool": stock_tool,
    "ComparisonTool": comparison_tool,
}


PARAM_EXTRACTION_PROMPT = """You are a parameter extractor for an e-commerce retrieval tool.

Given:
- User query: "{query}"
- Tool to call: {tool_name}
- Step description: "{step}"
- Previous tool outputs (summary): {prev_summary}

Extract the correct parameters for this tool as a JSON object.

Tool parameter schemas:
- SQLFilterTool: {{ "min_price": float|null, "max_price": float|null, "brand": str|null, "category": str|null, "attributes": {{key:val}}|null, "min_rating": float|null, "in_stock": bool|null, "order_by": str, "limit": int }}
  IMPORTANT for attributes: Product specs are stored as key-value pairs. Common keys: "RAM", "Storage", "Processor", "Display Size", "Display Type", "Battery", "Battery Life", "Color", "Graphics", "Weight", "Connectivity", "Noise Cancellation".
  Examples: {{"attributes": {{"RAM": "16GB DDR5"}}}}, {{"attributes": {{"Processor": "i7", "RAM": "16GB"}}}}, {{"attributes": {{"Display Type": "AMOLED"}}}}
  Note: Use icontains matching, so partial values like "DDR5" will match "16GB DDR5".

- ProductEmbeddingSearchTool: {{ "query": str, "top_k": int }}
- ReviewEmbeddingSearchTool: {{ "query": str, "top_k": int, "min_rating": float|null }}
- ImageEmbeddingSearchTool: {{ "image_description": str|null, "text_constraint": str|null, "top_k": int }}
- BM25KeywordSearchTool: {{ "query": str, "top_k": int }}
- HybridSearchFusionTool: {{ "query": str, "top_k": int }}
- StockCheckTool: {{ "title_contains": str|null, "brand": str|null, "only_in_stock": bool, "limit": int }}
- ComparisonTool: {{ "product_ids": [str] }}

Output ONLY valid JSON. No explanation."""


def _detect_tool(step: str) -> Optional[str]:
    """Match step description to a tool name."""
    for tool_name in _TOOL_MAP:
        if tool_name in step:
            return tool_name
    # Fuzzy keyword fallback
    step_lower = step.lower()
    if "sql" in step_lower or "filter" in step_lower or "price" in step_lower:
        return "SQLFilterTool"
    if "review" in step_lower and "embed" in step_lower:
        return "ReviewEmbeddingSearchTool"
    if "image" in step_lower or "visual" in step_lower:
        return "ImageEmbeddingSearchTool"
    if "bm25" in step_lower or "keyword" in step_lower:
        return "BM25KeywordSearchTool"
    if "hybrid" in step_lower or "fusion" in step_lower:
        return "HybridSearchFusionTool"
    if "stock" in step_lower or "inventory" in step_lower:
        return "StockCheckTool"
    if "compar" in step_lower:
        return "ComparisonTool"
    if "product" in step_lower and "embed" in step_lower:
        return "ProductEmbeddingSearchTool"
    if "rank" in step_lower:
        return None  # ranking is a post-processing step, not a tool
    return None


def _summarize_previous(tool_outputs: List[Dict[str, Any]], max_items: int = 3) -> str:
    """Create a short summary of prior tool outputs for LLM context."""
    if not tool_outputs:
        return "None"
    parts = []
    for to in tool_outputs[-max_items:]:
        tool = to.get("tool", "unknown")
        count = to.get("result", {}).get("count", 0)
        parts.append(f"{tool}: {count} results")
    return "; ".join(parts)


def _extract_product_ids(tool_outputs: List[Dict[str, Any]]) -> List[str]:
    """Collect product IDs from previous tool outputs for ComparisonTool."""
    ids = []
    for to in tool_outputs:
        result = to.get("result", {})
        for key in ("products", "results"):
            for item in result.get(key, []):
                pid = item.get("id") or item.get("source_id") or item.get("product_id")
                if pid and pid not in ids:
                    ids.append(pid)
    return ids


def _extract_params_llm(query: str, tool_name: str, step: str, prev_summary: str) -> Dict[str, Any]:
    """Use LLM to extract parameters for the tool call."""
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)
    prompt = PARAM_EXTRACTION_PROMPT.format(
        query=query, tool_name=tool_name, step=step, prev_summary=prev_summary,
    )
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_completion_tokens=300,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content.strip()
    return json.loads(raw)


def _extract_params_fallback(query: str, tool_name: str, state: AgentState) -> Dict[str, Any]:
    """Deterministic fallback parameter extraction."""
    if tool_name in ("ProductEmbeddingSearchTool", "BM25KeywordSearchTool", "HybridSearchFusionTool"):
        return {"query": query}
    if tool_name == "ReviewEmbeddingSearchTool":
        return {"query": query}
    if tool_name == "ImageEmbeddingSearchTool":
        return {"image_base64": state.get("image_data"), "text_constraint": query}
    if tool_name == "StockCheckTool":
        return {"title_contains": query, "only_in_stock": True}
    if tool_name == "ComparisonTool":
        return {"product_ids": _extract_product_ids(state.get("tool_outputs", []))}
    # SQLFilterTool default
    return {}


def act(state: AgentState) -> AgentState:
    """
    LangGraph node: execute the current plan step.
    Updates state["tool_outputs"] and increments state["current_step_index"].
    """
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    query = state.get("query", "")
    tool_outputs = state.get("tool_outputs", [])

    if idx >= len(plan):
        return state

    step = plan[idx]
    logger.info(f"ActAgent step {idx}: {step}")

    # Detect which tool this step needs
    tool_name = _detect_tool(step)

    if tool_name is None:
        # Non-tool step (e.g. "Rank final candidates", "Direct LLM response")
        tool_outputs.append({
            "tool": "noop",
            "step": step,
            "result": {"note": "Non-tool step, skipped"},
        })
        state["tool_outputs"] = tool_outputs
        state["current_step_index"] = idx + 1
        return state

    # Extract parameters
    try:
        prev_summary = _summarize_previous(tool_outputs)
        params = _extract_params_llm(query, tool_name, step, prev_summary)
    except Exception as e:
        logger.warning(f"LLM param extraction failed ({e}), using fallback")
        params = _extract_params_fallback(query, tool_name, state)

    # Clean None values
    params = {k: v for k, v in params.items() if v is not None}

    # Special handling: ComparisonTool needs product_ids from prior results.
    # The LLM may return product names ("iPhone 14") instead of UUIDs.
    # Prefer real UUIDs from prior tool outputs when available;
    # otherwise keep whatever the LLM gave — ComparisonTool can
    # resolve product names to UUIDs via title search.
    if tool_name == "ComparisonTool":
        prior_ids = _extract_product_ids(tool_outputs)
        if prior_ids:
            params["product_ids"] = prior_ids
        elif not params.get("product_ids"):
            params["product_ids"] = []

    # Execute tool
    try:
        tool_module = _TOOL_MAP[tool_name]
        result = tool_module.run(**params)
    except Exception as e:
        logger.exception(f"Tool {tool_name} execution failed")
        result = {"tool": tool_name, "error": str(e), "count": 0}

    tool_outputs.append({
        "tool": tool_name,
        "step": step,
        "params": params,
        "result": result,
    })

    state["tool_outputs"] = tool_outputs
    state["current_step_index"] = idx + 1
    return state
