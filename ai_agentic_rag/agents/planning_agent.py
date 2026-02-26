"""
Planning Agent — second node in the agentic pipeline.

Responsibilities:
  - Break complex queries into ordered sub-steps
  - Decide retrieval order and tool sequence
  - Output a plan list stored in state["plan"]
"""
import json
import logging
from typing import List

from ai_agentic_rag.config import GROQ_API_KEY, LLM_MODEL
from ai_agentic_rag.state import AgentState

logger = logging.getLogger(__name__)

PLAN_SYSTEM_PROMPT = """You are the Planning Agent for an electronics e-commerce RAG system.

Given the user query and an analysis object (intent, modality, complexity, required_sources),
produce an ORDERED list of retrieval/processing steps.

Available tools (use these exact names in your steps):
- SQLFilterTool: structured DB queries (price, brand, category, stock, attributes like RAM, processor, storage)
- ProductEmbeddingSearchTool: semantic product search (understands meaning, not just keywords)
- ReviewEmbeddingSearchTool: review sentiment retrieval
- ImageEmbeddingSearchTool: visual similarity search
- BM25KeywordSearchTool: exact keyword matching (model numbers, spec values)
- HybridSearchFusionTool: combined BM25 + vector scoring (PREFERRED over individual BM25/vector for most queries)
- StockCheckTool: inventory availability
- ComparisonTool: multi-product comparison

Rules:
1. For "factual" intent → return ["Direct LLM response"]
2. For "stock_check" → only SQLFilterTool / StockCheckTool steps
3. For "comparison" → SQL first, then HybridSearchFusionTool, then ComparisonTool
4. For "recommendation" → SQL filter first, then HybridSearchFusionTool, then review
5. For "visual_search" → ImageEmbeddingSearchTool first, then optional hybrid
6. For "product_search" → prefer HybridSearchFusionTool; add SQLFilterTool if price/brand/attribute filters needed
7. When specs are mentioned (RAM, storage, processor, display, battery), use SQLFilterTool with attribute filtering AND HybridSearchFusionTool
8. Always end with "Rank final candidates" for retrieval queries
9. Each step should be a short, actionable sentence mentioning the tool name

Output ONLY a JSON array of strings. No explanation."""

PLAN_USER_TEMPLATE = """Query: "{query}"
Analysis: {analysis}

Generate the retrieval plan."""


# ── Fallback deterministic planner (no LLM needed) ────────────────

_FALLBACK_PLANS = {
    "factual": ["Direct LLM response"],
    "stock_check": [
        "Run StockCheckTool for inventory lookup",
        "Rank final candidates",
    ],
    "product_search": [
        "Run HybridSearchFusionTool for combined semantic and keyword search",
        "Rank final candidates",
    ],
    "comparison": [
        "Apply SQLFilterTool to fetch candidate products",
        "Run HybridSearchFusionTool for semantic and keyword enrichment",
        "Run ComparisonTool for side-by-side comparison",
        "Rank final candidates",
    ],
    "visual_search": [
        "Run ImageEmbeddingSearchTool for visual matching",
        "Rank final candidates",
    ],
    "recommendation": [
        "Apply SQLFilterTool for initial filtering",
        "Run HybridSearchFusionTool for semantic and keyword matching",
        "Run ReviewEmbeddingSearchTool for review sentiment",
        "Rank final candidates",
    ],
    "review_based": [
        "Run ReviewEmbeddingSearchTool for review retrieval",
        "Rank final candidates",
    ],
}


def _build_fallback_plan(state: AgentState) -> List[str]:
    analysis = state.get("analysis", {})
    intent = analysis.get("intent", "product_search")
    sources = analysis.get("required_sources", [])

    plan = list(_FALLBACK_PLANS.get(intent, _FALLBACK_PLANS["product_search"]))

    # Inject SQL step if sql source requested but not in base plan
    if "sql" in sources and not any("SQL" in s for s in plan):
        plan.insert(0, "Apply SQLFilterTool for structured filtering by price, brand, category, or attributes")

    # Inject hybrid step if hybrid source requested but not in base plan
    if "hybrid" in sources and not any("Hybrid" in s for s in plan):
        plan.insert(-1, "Run HybridSearchFusionTool for combined ranking")

    # Inject BM25 step if bm25 source requested but not in base plan
    # (only if HybridSearchFusionTool is not already present, since hybrid includes BM25)
    if "bm25" in sources and not any("BM25" in s for s in plan) and not any("Hybrid" in s for s in plan):
        plan.insert(0, "Run BM25KeywordSearchTool for exact keyword matching")

    return plan


def plan(state: AgentState) -> AgentState:
    """
    LangGraph node: build the retrieval plan.
    Updates state["plan"] and state["current_step_index"].
    """
    query = state.get("query", "")
    analysis = state.get("analysis", {})

    # Factual queries need no planning
    if analysis.get("intent") == "factual":
        state["plan"] = ["Direct LLM response"]
        state["current_step_index"] = 0
        return state

    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)
        system = PLAN_SYSTEM_PROMPT
        user = PLAN_USER_TEMPLATE.format(query=query, analysis=json.dumps(analysis))

        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_completion_tokens=400,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        parsed = json.loads(raw)

        # Handle {"plan": [...]} or just [...]
        if isinstance(parsed, dict):
            steps = parsed.get("plan", parsed.get("steps", []))
        elif isinstance(parsed, list):
            steps = parsed
        else:
            steps = []

        if not steps:
            raise ValueError("Empty plan from LLM")

        state["plan"] = steps
        logger.info(f"PlanningAgent → {len(steps)} steps")

    except Exception as e:
        logger.warning(f"PlanningAgent LLM failed ({e}), using fallback planner")
        state["plan"] = _build_fallback_plan(state)

    state["current_step_index"] = 0
    state["tool_outputs"] = state.get("tool_outputs", [])
    return state
