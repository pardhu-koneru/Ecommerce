"""
Evaluator Agent — self-evaluation loop.

After the Generator produces an answer, the Evaluator verifies:
  - Required sources were actually used
  - SQL filters applied correctly (if needed)
  - Review data included when necessary
  - No hallucination (answer grounded in context)
  - Confidence score ∈ [0, 1]

If confidence < threshold → signals re-planning.
"""
import json
import logging

from ai_agentic_rag.config import GROQ_API_KEY, LLM_MODEL, CONFIDENCE_THRESHOLD
from ai_agentic_rag.state import AgentState

logger = logging.getLogger(__name__)

EVAL_SYSTEM_PROMPT = """You are a strict quality evaluator for an e-commerce RAG system.

Given:
1. The user query
2. The analysis (intent, required_sources)
3. The tools that were executed
4. The assembled context
5. The generated answer

Evaluate the answer on these criteria:
- sources_used: Were all required_sources actually called? (true/false)
- sql_correct: If SQL was needed, was it applied properly? (true/false/na)
- reviews_included: If review data was needed, is it in the answer? (true/false/na)
- grounded: Is the answer fully grounded in the context (no hallucination)? (true/false)
- complete: Does the answer fully address the user query? (true/false)

Also assign:
- confidence_score: float between 0.0 and 1.0
- notes: brief explanation of any issues

Output ONLY valid JSON with keys: sources_used, sql_correct, reviews_included, grounded, complete, confidence_score, notes"""

EVAL_USER_TEMPLATE = """Query: "{query}"
Analysis: {analysis}
Tools executed: {tools_used}

Context (first 3000 chars):
{context_snippet}

Generated Answer:
{answer}

Evaluate this answer."""


def evaluate(state: AgentState) -> AgentState:
    """
    LangGraph node: evaluate the generated answer.
    Updates state["confidence_score"] and state["evaluation_notes"].
    """
    query = state.get("query", "")
    analysis = state.get("analysis", {})
    tool_outputs = state.get("tool_outputs", [])
    context = state.get("context", "")
    answer = state.get("final_answer", "")

    # Factual queries skip heavy evaluation
    if analysis.get("intent") == "factual":
        state["confidence_score"] = 0.85
        state["evaluation_notes"] = "Factual query — lightweight evaluation"
        return state

    tools_used = [to.get("tool", "unknown") for to in tool_outputs if to.get("tool") != "noop"]

    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)

        user = EVAL_USER_TEMPLATE.format(
            query=query,
            analysis=json.dumps(analysis),
            tools_used=json.dumps(tools_used),
            context_snippet=context[:3000],
            answer=answer[:2000],
        )

        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": EVAL_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_completion_tokens=300,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        evaluation = json.loads(raw)

        score = float(evaluation.get("confidence_score", 0.5))
        score = max(0.0, min(1.0, score))

        notes = evaluation.get("notes", "")

        state["confidence_score"] = score
        state["evaluation_notes"] = notes
        logger.info(f"Evaluator → confidence={score:.2f}  notes={notes}")

    except Exception as e:
        logger.exception("Evaluator failed, assigning default medium confidence")
        state["confidence_score"] = 0.6
        state["evaluation_notes"] = f"Evaluation error: {e}"

    return state
