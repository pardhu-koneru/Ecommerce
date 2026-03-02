"""
LangGraph Node definitions — thin wrappers that import and call
the agent / service functions, plus the ToolRouter and LoopController.

Performance optimizations:
  - ToolRouterNode now parallelizes independent tool steps using ThreadPoolExecutor
  - LoopController uses intent-specific confidence thresholds
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from ai_agentic_rag.state import AgentState
from ai_agentic_rag.config import (
    CONFIDENCE_THRESHOLD,
    MAX_LOOP_ITERATIONS,
    INTENT_CONFIDENCE_THRESHOLDS,
)

logger = logging.getLogger(__name__)


# ── 1. AnalyzeNode ────────────────────────────────────────────────

def analyze_node(state: AgentState) -> AgentState:
    from ai_agentic_rag.agents.analyze_agent import analyze
    return analyze(state)


# ── 2. PlanningNode ───────────────────────────────────────────────

def planning_node(state: AgentState) -> AgentState:
    from ai_agentic_rag.agents.planning_agent import plan
    return plan(state)


# ── 3. ToolRouterNode ─────────────────────────────────────────────

# Tools that depend on the output of earlier tools (must run sequentially AFTER others)
_DEPENDENT_TOOLS = {"ComparisonTool", "StockCheckTool"}


def _classify_steps(plan):
    """
    Split plan into independent steps (can run in parallel) and
    dependent steps (need prior results, must run after).
    Non-tool steps (rank, direct LLM) are kept as dependent to preserve order.
    """
    from ai_agentic_rag.agents.act_agent import _detect_tool

    independent = []
    dependent = []

    for idx, step in enumerate(plan):
        tool_name = _detect_tool(step)
        if tool_name is None or tool_name in _DEPENDENT_TOOLS:
            dependent.append((idx, step))
        else:
            independent.append((idx, step))

    return independent, dependent


def _execute_single_step(state_snapshot, step_idx, step_text):
    """
    Execute a single plan step in isolation.
    Takes a state snapshot and returns the tool output dict.
    Used by ThreadPoolExecutor for parallel execution.

    IMPORTANT: Handles Django DB connection lifecycle for thread safety.
    Each worker thread gets its own DB connection which is cleaned up after use.
    """
    import django.db
    from ai_agentic_rag.agents.act_agent import (
        _detect_tool, _extract_params_llm, _extract_params_fallback,
        _summarize_previous, _TOOL_MAP,
    )

    # Ensure this thread has a fresh DB connection
    django.db.close_old_connections()

    try:
        query = state_snapshot["query"]
        tool_outputs = state_snapshot.get("tool_outputs", [])
        tool_name = _detect_tool(step_text)

        if tool_name is None:
            return {
                "tool": "noop",
                "step": step_text,
                "result": {"note": "Non-tool step, skipped"},
            }

        # Parameter extraction — same strategy as act agent:
        # LLM for SQL (structured parsing), deterministic for others.
        # Note: ComparisonTool is in _DEPENDENT_TOOLS so never runs here.
        _LLM_REQUIRED_TOOLS = {"SQLFilterTool", "ComparisonTool"}
        if tool_name in _LLM_REQUIRED_TOOLS:
            try:
                prev_summary = _summarize_previous(tool_outputs)
                params = _extract_params_llm(query, tool_name, step_text, prev_summary)
            except Exception as e:
                logger.warning(f"LLM param extraction failed ({e}), using fallback")
                params = _extract_params_fallback(query, tool_name, state_snapshot)
        else:
            params = _extract_params_fallback(query, tool_name, state_snapshot)

        params = {k: v for k, v in params.items() if v is not None}

        try:
            tool_module = _TOOL_MAP[tool_name]
            result = tool_module.run(**params)
        except Exception as e:
            logger.exception(f"Tool {tool_name} execution failed")
            result = {"tool": tool_name, "error": str(e), "count": 0}

        return {
            "tool": tool_name,
            "step": step_text,
            "params": params,
            "result": result,
        }
    finally:
        # Clean up DB connection for this worker thread
        django.db.close_old_connections()


def tool_router_node(state: AgentState) -> AgentState:
    """
    Executes plan steps with parallelism for independent tools.

    Strategy:
      1. Classify steps into independent (SQL, Hybrid, BM25, Embedding, Review, Image)
         and dependent (Comparison, Stock — need prior product IDs).
      2. Run all independent steps in parallel via ThreadPoolExecutor.
      3. Run dependent steps sequentially (they need prior outputs).
    """
    from ai_agentic_rag.agents.act_agent import act

    plan = state.get("plan", [])
    state["current_step_index"] = 0
    state.setdefault("tool_outputs", [])

    if not plan:
        return state

    independent, dependent = _classify_steps(plan)

    # ── Phase 1: Run independent steps in parallel ────────────────
    if independent:
        # Create a read-only snapshot for parallel workers
        state_snapshot = {
            "query": state.get("query", ""),
            "image_data": state.get("image_data"),
            "analysis": state.get("analysis", {}),
            "tool_outputs": list(state.get("tool_outputs", [])),
        }

        parallel_results = {}
        with ThreadPoolExecutor(max_workers=min(len(independent), 4)) as executor:
            futures = {
                executor.submit(
                    _execute_single_step, state_snapshot, idx, step_text
                ): idx
                for idx, step_text in independent
            }
            for future in as_completed(futures):
                step_idx = futures[future]
                try:
                    parallel_results[step_idx] = future.result()
                except Exception as e:
                    logger.exception(f"Parallel step {step_idx} failed")
                    parallel_results[step_idx] = {
                        "tool": "error",
                        "step": plan[step_idx],
                        "result": {"error": str(e), "count": 0},
                    }

        # Append results in original plan order
        for idx, _ in sorted(independent, key=lambda x: x[0]):
            if idx in parallel_results:
                state["tool_outputs"].append(parallel_results[idx])

    # ── Phase 2: Run dependent steps sequentially ─────────────────
    for idx, step_text in dependent:
        state["current_step_index"] = idx
        state = act(state)

    # Final index
    state["current_step_index"] = len(plan)
    return state


# ── 4-9. Individual tool nodes (used if graph routes per-tool) ────

def sql_tool_node(state: AgentState) -> AgentState:
    from ai_agentic_rag.tools import sql_tool
    result = sql_tool.run()
    state.setdefault("tool_outputs", []).append({"tool": "SQLFilterTool", "result": result})
    return state


def product_embedding_node(state: AgentState) -> AgentState:
    from ai_agentic_rag.tools import product_vector_tool
    result = product_vector_tool.run(query=state.get("query", ""))
    state.setdefault("tool_outputs", []).append({"tool": "ProductEmbeddingSearchTool", "result": result})
    return state


def review_embedding_node(state: AgentState) -> AgentState:
    from ai_agentic_rag.tools import review_vector_tool
    result = review_vector_tool.run(query=state.get("query", ""))
    state.setdefault("tool_outputs", []).append({"tool": "ReviewEmbeddingSearchTool", "result": result})
    return state


def bm25_node(state: AgentState) -> AgentState:
    from ai_agentic_rag.tools import bm25_tool
    result = bm25_tool.run(query=state.get("query", ""))
    state.setdefault("tool_outputs", []).append({"tool": "BM25KeywordSearchTool", "result": result})
    return state


def hybrid_fusion_node(state: AgentState) -> AgentState:
    from ai_agentic_rag.tools import hybrid_fusion_tool
    result = hybrid_fusion_tool.run(query=state.get("query", ""))
    state.setdefault("tool_outputs", []).append({"tool": "HybridSearchFusionTool", "result": result})
    return state


def image_embedding_node(state: AgentState) -> AgentState:
    from ai_agentic_rag.tools import image_vector_tool
    result = image_vector_tool.run(
        image_base64=state.get("image_data"),
        text_constraint=state.get("query", ""),
    )
    state.setdefault("tool_outputs", []).append({"tool": "ImageEmbeddingSearchTool", "result": result})
    return state


# ── 10. ContextBuilderNode ────────────────────────────────────────

def context_builder_node(state: AgentState) -> AgentState:
    from ai_agentic_rag.services.context_builder import build_context
    return build_context(state)


# ── 11. GeneratorNode ─────────────────────────────────────────────

def generator_node(state: AgentState) -> AgentState:
    from ai_agentic_rag.services.generator import generate
    return generate(state)


# ── 12. SelfEvaluatorNode ─────────────────────────────────────────

def self_evaluator_node(state: AgentState) -> AgentState:
    from ai_agentic_rag.agents.evaluator_agent import evaluate
    return evaluate(state)


# ── 13. LoopControllerNode ────────────────────────────────────────

def _get_confidence_threshold(state: AgentState) -> float:
    """Return the confidence threshold for this query's intent."""
    intent = state.get("analysis", {}).get("intent", "")
    return INTENT_CONFIDENCE_THRESHOLDS.get(intent, CONFIDENCE_THRESHOLD)


def loop_controller_node(state: AgentState) -> AgentState:
    """
    Decides whether to accept the answer or loop back for refinement.
    Increments loop_count on each pass.
    Uses intent-specific confidence thresholds to reduce unnecessary re-plan loops.
    """
    loop_count = state.get("loop_count", 0)
    confidence = state.get("confidence_score", 0.0)
    threshold = _get_confidence_threshold(state)

    state["loop_count"] = loop_count + 1

    if confidence >= threshold:
        logger.info(f"LoopController → ACCEPT (confidence={confidence:.2f} >= threshold={threshold:.2f})")
    elif loop_count >= MAX_LOOP_ITERATIONS:
        logger.warning(
            f"LoopController → ACCEPT (max loops={MAX_LOOP_ITERATIONS} reached, "
            f"confidence={confidence:.2f})"
        )
    else:
        logger.info(
            f"LoopController → RE-PLAN (confidence={confidence:.2f} < threshold={threshold:.2f}, "
            f"loop={loop_count + 1})"
        )

    return state


def should_loop(state: AgentState) -> str:
    """
    Conditional edge function for LangGraph.
    Returns "replan" or "end".
    Uses intent-specific thresholds.
    """
    confidence = state.get("confidence_score", 0.0)
    loop_count = state.get("loop_count", 0)
    threshold = _get_confidence_threshold(state)

    if confidence >= threshold:
        return "end"
    if loop_count >= MAX_LOOP_ITERATIONS:
        return "end"
    return "replan"
