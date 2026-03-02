"""
Central configuration for the Agentic RAG system.
All tunable parameters in one place.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM / Embedding providers ──────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIM = 768

# Groq LLM model for agents (analyze, plan, generate, evaluate)
LLM_MODEL = "llama-3.3-70b-versatile"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
# Lightweight model for parameter extraction (much faster)
PARAM_EXTRACTION_MODEL = "llama-3.1-8b-instant"

# ── Retrieval tuning ──────────────────────────────────────────────
# Hybrid search weights   FinalScore = α·vector + β·BM25
HYBRID_ALPHA = 0.6   # vector weight
HYBRID_BETA = 0.4    # BM25 weight

# Default top-k for various search tools
VECTOR_TOP_K = 10
BM25_TOP_K = 10
HYBRID_TOP_K = 10
IMAGE_TOP_K = 5

# ── Self-evaluation ───────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.75  # default; below this → re-plan & re-retrieve
MAX_LOOP_ITERATIONS = 2      # safety cap on agent loops (reduced from 3)

# Intent-specific thresholds — some intents are inherently less "complete"
# so we accept lower confidence on first pass to avoid expensive re-plan loops.
INTENT_CONFIDENCE_THRESHOLDS = {
    "comparison": 0.65,       # comparisons are naturally partial
    "recommendation": 0.65,   # subjective, lower bar
    "review_based": 0.65,     # review summaries are adequate
    "factual": 0.5,           # auto-scored at 0.85 anyway
    "stock_check": 0.6,       # simple yes/no
}

# ── Misc ──────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("RAG_LOG_LEVEL", "INFO")

# Query type constants
QUERY_TYPES = [
    "factual",
    "product_search",
    "comparison",
    "visual_search",
    "stock_check",
    "recommendation",
    "review_based",
]

# Source constants
SOURCE_SQL = "sql"
SOURCE_PRODUCT_EMBEDDING = "product_embedding"
SOURCE_REVIEW_EMBEDDING = "review_embedding"
SOURCE_IMAGE_EMBEDDING = "image_embedding"
SOURCE_BM25 = "bm25"
SOURCE_HYBRID = "hybrid"
