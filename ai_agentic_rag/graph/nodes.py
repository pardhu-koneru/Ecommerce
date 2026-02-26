"""
LangGraph Node definitions — thin wrappers that import and call
the agent / service functions, plus the ToolRouter and LoopController.
"""
import logging

from ai_agentic_rag.state import AgentState
from ai_agentic_rag.config import CONFIDENCE_THRESHOLD, MAX_LOOP_ITERATIONS

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

def tool_router_node(state: AgentState) -> AgentState:
    """
    Iterates through the plan and executes each step via the Act Agent.
    Runs ALL steps sequentially before moving to context building.
    """
    from ai_agentic_rag.agents.act_agent import act

    plan = state.get("plan", [])
    state["current_step_index"] = 0
    state.setdefault("tool_outputs", [])

    for i in range(len(plan)):
        state = act(state)

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

def loop_controller_node(state: AgentState) -> AgentState:
    """
    Decides whether to accept the answer or loop back for refinement.
    Increments loop_count on each pass.
    """
    loop_count = state.get("loop_count", 0)
    confidence = state.get("confidence_score", 0.0)

    state["loop_count"] = loop_count + 1

    if confidence >= CONFIDENCE_THRESHOLD:
        logger.info(f"LoopController → ACCEPT (confidence={confidence:.2f})")
    elif loop_count >= MAX_LOOP_ITERATIONS:
        logger.warning(
            f"LoopController → ACCEPT (max loops={MAX_LOOP_ITERATIONS} reached, "
            f"confidence={confidence:.2f})"
        )
    else:
        logger.info(
            f"LoopController → RE-PLAN (confidence={confidence:.2f}, "
            f"loop={loop_count + 1})"
        )

    return state


def should_loop(state: AgentState) -> str:
    """
    Conditional edge function for LangGraph.
    Returns "replan" or "end".
    """
    confidence = state.get("confidence_score", 0.0)
    loop_count = state.get("loop_count", 0)

    if confidence >= CONFIDENCE_THRESHOLD:
        return "end"
    if loop_count >= MAX_LOOP_ITERATIONS:
        return "end"
    return "replan"
