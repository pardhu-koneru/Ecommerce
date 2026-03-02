"""
LangGraph Workflow — the main orchestrator.

Graph flow:
  AnalyzeNode → PlanningNode → ToolRouterNode → ContextBuilderNode
  → GeneratorNode → SelfEvaluatorNode → LoopControllerNode
                                                  │
                                        ┌─────────┴─────────┐
                                        │                    │
                                    "replan"              "end"
                                        │                    │
                                  PlanningNode          ◉ FINISH
                                        ↓
                               (loop back through)

Usage:
    from ai_agentic_rag.graph.workflow import run_query
    result = run_query("best gaming laptop under 80000")
"""
import logging

from langgraph.graph import StateGraph, END

from ai_agentic_rag.state import AgentState
from ai_agentic_rag.graph.nodes import (
    analyze_node,
    planning_node,
    tool_router_node,
    context_builder_node,
    generator_node,
    self_evaluator_node,
    loop_controller_node,
    should_loop,
)

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """Construct and compile the full agentic RAG graph."""
    graph = StateGraph(AgentState)

    # ── Add nodes ─────────────────────────────────────
    graph.add_node("analyze", analyze_node)
    graph.add_node("plan", planning_node)
    graph.add_node("execute_tools", tool_router_node)
    graph.add_node("build_context", context_builder_node)
    graph.add_node("generate", generator_node)
    graph.add_node("evaluate", self_evaluator_node)
    graph.add_node("loop_control", loop_controller_node)

    # ── Define edges ──────────────────────────────────
    graph.set_entry_point("analyze")

    graph.add_edge("analyze", "plan")
    graph.add_edge("plan", "execute_tools")
    graph.add_edge("execute_tools", "build_context")
    graph.add_edge("build_context", "generate")
    graph.add_edge("generate", "evaluate")
    graph.add_edge("evaluate", "loop_control")

    # Conditional: loop back or finish
    graph.add_conditional_edges(
        "loop_control",
        should_loop,
        {
            "replan": "plan",      # low confidence → re-plan and re-execute
            "end": END,            # high confidence → done
        },
    )

    return graph.compile()


# Module-level compiled graph (lazy singleton)
_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def run_query(
    query: str,
    image_data: str | None = None,
) -> dict:
    """
    Main entry point — run a query through the full agentic RAG pipeline.

    Args:
        query: user's natural-language question
        image_data: optional base64-encoded image for visual search

    Returns:
        dict with keys: final_answer, confidence_score, analysis,
                        plan, tool_outputs, evaluation_notes, loop_count
    """
    initial_state: AgentState = {
        "query": query,
        "image_data": image_data,
        "analysis": {},
        "plan": [],
        "current_step_index": 0,
        "tool_outputs": [],
        "context": "",
        "final_answer": "",
        "confidence_score": 0.0,
        "evaluation_notes": "",
        "loop_count": 0,
    }

    # Clear per-request embedding cache to avoid stale data across requests
    from ai_agentic_rag.tools.product_vector_tool import clear_embedding_cache
    clear_embedding_cache()

    graph = get_graph()
    final_state = graph.invoke(initial_state)

    return {
        "answer": final_state.get("final_answer", ""),
        "confidence": final_state.get("confidence_score", 0.0),
        "intent": final_state.get("analysis", {}).get("intent", ""),
        "plan": final_state.get("plan", []),
        "tools_used": [
            to.get("tool") for to in final_state.get("tool_outputs", [])
            if to.get("tool") != "noop"
        ],
        "tool_outputs": final_state.get("tool_outputs", []),
        "loop_count": final_state.get("loop_count", 0),
        "evaluation_notes": final_state.get("evaluation_notes", ""),
    }
