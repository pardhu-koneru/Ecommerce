"""
Generator — produces the final user-facing answer using Groq LLM,
grounded entirely in the retrieved context.
"""
import logging

from ai_agentic_rag.config import GROQ_API_KEY, LLM_MODEL
from ai_agentic_rag.state import AgentState

logger = logging.getLogger(__name__)

GENERATOR_SYSTEM_PROMPT = """You are a helpful electronics e-commerce assistant.

RULES:
1. Answer ONLY based on the CONTEXT provided below. Do NOT hallucinate.
2. If the context is insufficient, say so honestly — but FIRST check carefully: the context includes full product specifications (RAM, processor, storage, display, battery, etc.) under SPECIFICATIONS sections.
3. When listing products, include name, brand, price, rating, and key specs from the SPECIFICATIONS section.
4. For comparisons, use a clear side-by-side format highlighting differences.
5. For stock queries, explicitly state availability.
6. For review-based queries, summarize sentiment and mention ratings.
7. Be concise, factual, and helpful. Format with bullet points or tables where appropriate.
8. Never invent product names, prices, or specs not present in context.
9. If a product's specs match the query criteria, include it in your answer even if the exact wording differs slightly (e.g., "DDR5" matches "LPDDR5", "16GB RAM" matches "RAM: 16GB DDR5").

CONTEXT:
{context}"""

GENERATOR_USER_TEMPLATE = """{query}"""


def generate(state: AgentState) -> AgentState:
    """
    LangGraph node: generate the final answer.
    Updates state["final_answer"].
    """
    query = state.get("query", "")
    context = state.get("context", "")
    analysis = state.get("analysis", {})

    # Factual queries → lightweight direct answer (no context)
    if analysis.get("intent") == "factual" and not context.strip():
        return _generate_factual(state, query)

    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)

        messages = [
            {"role": "system", "content": GENERATOR_SYSTEM_PROMPT.format(context=context)},
            {"role": "user", "content": GENERATOR_USER_TEMPLATE.format(query=query)},
        ]

        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.3,
            max_completion_tokens=1024,
        )

        answer = response.choices[0].message.content.strip()
        state["final_answer"] = answer
        logger.info(f"Generator → {len(answer)} chars answer")

    except Exception as e:
        logger.exception("Generator failed")
        state["final_answer"] = (
            "I'm sorry, I encountered an error generating your answer. "
            "Please try again."
        )

    return state


def _generate_factual(state: AgentState, query: str) -> AgentState:
    """Handle factual queries with a direct LLM call (no retrieval context)."""
    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)

        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a knowledgeable electronics assistant. "
                        "Answer factual questions concisely and accurately."
                    ),
                },
                {"role": "user", "content": query},
            ],
            temperature=0.2,
            max_completion_tokens=512,
        )

        state["final_answer"] = response.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("Factual generator failed")
        state["final_answer"] = "Sorry, I couldn't process your question right now."

    return state
