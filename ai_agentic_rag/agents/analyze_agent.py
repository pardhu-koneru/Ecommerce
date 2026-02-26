"""
Analyze Agent — first node in the agentic pipeline.

Responsibilities:
  - Classify query intent (factual, product_search, comparison, etc.)
  - Detect modality (text / image / both)
  - Detect complexity (single_step / multi_step)
  - Identify required retrieval sources
"""
import json
import logging
import re
from typing import Dict, Any

from ai_agentic_rag.config import (
    GROQ_API_KEY,
    LLM_MODEL,
    QUERY_TYPES,
    SOURCE_SQL,
    SOURCE_PRODUCT_EMBEDDING,
    SOURCE_REVIEW_EMBEDDING,
    SOURCE_IMAGE_EMBEDDING,
    SOURCE_BM25,
    SOURCE_HYBRID,
)
from ai_agentic_rag.state import AgentState, AnalysisResult

logger = logging.getLogger(__name__)

# ── Regex patterns that signal BM25 should be included ─────────────
_BM25_PATTERNS = [
    r"\b[A-Z]{2,}\s*\d{3,}",           # model numbers: RTX 3050, RX 7900
    r"\b\d{2,}[GT]B\b",                 # storage/RAM: 256GB, 16GB
    r"\bDDR[345]\b",                     # RAM types: DDR3, DDR4, DDR5
    r"\bLPDDR\d",                        # mobile RAM: LPDDR5
    r"\bi[5-9]-\d{4,}",                 # Intel CPUs: i5-13600K
    r"\bRyzen\s*\d",                    # AMD CPUs
    r"\b[Ss][Kk][Uu]",                  # SKU patterns
    r"\biPhone\s*\d{1,2}\b",            # iPhone models
    r"\bGalaxy\s*[SZA]\d{1,2}",         # Samsung models
    r"\bPixel\s*\d",                    # Google Pixel
    r"\bMacBook",                       # Apple laptops
    r"\bAMOLED|OLED|IPS|LCD\b",         # display types
    r"\bSSD|NVMe|HDD\b",               # storage types
    r"\b\d{3,5}\s*mAh\b",              # battery capacity: 5000mAh
    r"\bNFC|5G|LTE|WiFi\s*\d",         # connectivity specs
    r"\bRTX|GTX\b",                     # GPU models
    r"\bSnapdragon|Dimensity|Helio\b",  # mobile processors
    r"\bThunderbolt|USB-C|HDMI\b",      # port types
    r"\bnoise\s*cancell",              # ANC features
    r"\bQHD|FHD|4K|UHD\b",             # resolution types
    r"\b\d{2,3}Hz\b",                   # refresh rates: 120Hz, 144Hz
    r"\b\d{1,3}\s*MP\b",               # camera megapixels: 50MP, 200MP
    r"\b\d{1,3}\s*[Ww]att|\d{1,3}W\b", # charging wattage: 65W
]

ANALYZE_SYSTEM_PROMPT = """You are the Analyze Agent for an electronics e-commerce RAG system.

Given a user query (and optional image flag), output a JSON object with these exact keys:
- "intent": one of {query_types}
- "modality": "text" | "image" | "both"
- "complexity": "single_step" | "multi_step"
- "requires_retrieval": true/false
- "required_sources": list from ["sql", "product_embedding", "review_embedding", "image_embedding", "bm25", "hybrid"]

ROUTING RULES:
- factual → no retrieval, direct LLM
- product_search → hybrid (always); add sql if price/brand/category/attribute filters detected
- comparison → sql + product_embedding + hybrid; optionally review_embedding
- visual_search → image_embedding; add hybrid if brand specified
- stock_check → sql only
- recommendation → sql + hybrid + review_embedding
- review_based → review_embedding; use metadata (avg_rating, review_count)

IMPORTANT:
- If the query mentions specific specs (RAM, storage, processor, display, battery, etc.), ALWAYS include "hybrid" and "bm25" sources for exact keyword matching
- If the query mentions price range, brand, or category, include "sql" for precise filtering
- Queries with multiple filter conditions (price + specs + brand) should be "multi_step" complexity
- "hybrid" combines both semantic search and keyword matching — prefer it over "product_embedding" alone

Output ONLY valid JSON, no explanation."""

ANALYZE_USER_TEMPLATE = """Query: "{query}"
Has image: {has_image}

Classify and route this query."""


def _has_bm25_signals(query: str) -> bool:
    """Check if the query contains patterns that warrant BM25 search."""
    for pat in _BM25_PATTERNS:
        if re.search(pat, query):
            return True
    return False


def analyze(state: AgentState) -> AgentState:
    """
    LangGraph node: analyze the incoming query.
    Updates state["analysis"].
    """
    query = state.get("query", "")
    has_image = bool(state.get("image_data"))

    try:
        from groq import Groq

        client = Groq(api_key=GROQ_API_KEY)

        system = ANALYZE_SYSTEM_PROMPT.format(query_types=QUERY_TYPES)
        user = ANALYZE_USER_TEMPLATE.format(query=query, has_image=has_image)

        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_completion_tokens=300,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        analysis: Dict[str, Any] = json.loads(raw)

        # Validate / sanitize
        if analysis.get("intent") not in QUERY_TYPES:
            analysis["intent"] = "product_search"

        analysis.setdefault("modality", "both" if has_image else "text")
        analysis.setdefault("complexity", "single_step")
        analysis.setdefault("requires_retrieval", True)
        analysis.setdefault("required_sources", [])

        # Inject BM25 if regex signals detected
        if _has_bm25_signals(query):
            sources = analysis["required_sources"]
            if SOURCE_BM25 not in sources:
                sources.append(SOURCE_BM25)
            if SOURCE_HYBRID not in sources and SOURCE_PRODUCT_EMBEDDING in sources:
                sources.append(SOURCE_HYBRID)

        # Factual → override
        if analysis["intent"] == "factual":
            analysis["requires_retrieval"] = False
            analysis["required_sources"] = []

        logger.info(f"AnalyzeAgent → {analysis}")
        state["analysis"] = AnalysisResult(**analysis)  # type: ignore[arg-type]

    except Exception as e:
        logger.exception("AnalyzeAgent failed, falling back to product_search")
        state["analysis"] = AnalysisResult(
            intent="product_search",
            modality="both" if has_image else "text",
            complexity="single_step",
            requires_retrieval=True,
            required_sources=[SOURCE_PRODUCT_EMBEDDING],
        )

    return state
