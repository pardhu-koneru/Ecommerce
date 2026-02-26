"""
Shared state object passed through all LangGraph nodes.
Uses TypedDict for type safety with LangGraph.
"""
from __future__ import annotations
from typing import TypedDict, List, Dict, Any, Optional


class AnalysisResult(TypedDict, total=False):
    intent: str                     # e.g. "product_search"
    modality: str                   # "text" | "image" | "both"
    complexity: str                 # "single_step" | "multi_step"
    requires_retrieval: bool
    required_sources: List[str]     # e.g. ["sql", "product_embedding"]


class AgentState(TypedDict, total=False):
    """Master state flowing through every node in the graph."""
    # ── Input ────────────────────────────────────────────
    query: str
    image_data: Optional[str]       # base64 image if visual search

    # ── Analysis ─────────────────────────────────────────
    analysis: AnalysisResult

    # ── Planning ─────────────────────────────────────────
    plan: List[str]                 # ordered step descriptions
    current_step_index: int         # which step we are executing

    # ── Tool outputs ─────────────────────────────────────
    tool_outputs: List[Dict[str, Any]]
    # Each entry: {"tool": "<name>", "result": {...}, "step": "<description>"}

    # ── Context & answer ─────────────────────────────────
    context: str                    # assembled context for LLM
    final_answer: str

    # ── Evaluation ───────────────────────────────────────
    confidence_score: float
    evaluation_notes: str
    loop_count: int                 # how many evaluate→re-plan cycles
