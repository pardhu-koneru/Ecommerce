"""
ImageEmbeddingSearchTool — visual similarity search.

Encodes a base64 image (via Groq vision → text description → embedding)
or takes an already-generated image description, and searches against
product document embeddings. Also supports optional brand/text constraint.
"""
import logging
from typing import Dict, Any, Optional

from products.models import AIDocumentEmbedding
from products.ai_service import AIService
from ai_agentic_rag.config import IMAGE_TOP_K

logger = logging.getLogger(__name__)

_ai_service: Optional[AIService] = None


def _get_ai_service() -> AIService:
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service


def run(
    *,
    image_description: Optional[str] = None,
    image_base64: Optional[str] = None,
    text_constraint: Optional[str] = None,
    top_k: int = IMAGE_TOP_K,
) -> Dict[str, Any]:
    """
    Visual similarity search.

    Provide EITHER:
      - image_description  (text description of the image already generated)
      - image_base64       (raw base64; will be converted via vision model)

    Optionally refine with text_constraint (e.g. brand name).

    Returns:
        {
            "tool": "ImageEmbeddingSearchTool",
            "count": int,
            "image_description": str,
            "results": [{ document_id, source_id, score, text_content, metadata }]
        }
    """
    try:
        ai = _get_ai_service()

        # ── Step 1: get a textual description ──────────────
        if image_description is None and image_base64 is None:
            return {
                "tool": "ImageEmbeddingSearchTool",
                "error": "Provide image_description or image_base64",
                "count": 0,
                "results": [],
            }

        desc = image_description
        if desc is None:
            # Use Groq vision to describe the image
            if ai.groq_client is None:
                return {
                    "tool": "ImageEmbeddingSearchTool",
                    "error": "Vision model unavailable (no Groq API key)",
                    "count": 0,
                    "results": [],
                }
            desc = _describe_base64_image(ai, image_base64)

        # ── Step 2: combine with text constraint ──────────
        search_text = desc
        if text_constraint:
            search_text = f"{text_constraint}. {desc}"

        # ── Step 3: embed and search ──────────────────────
        query_embedding = ai.generate_embedding(search_text)
        if not query_embedding or all(v == 0.0 for v in query_embedding):
            return {
                "tool": "ImageEmbeddingSearchTool",
                "error": "Failed to generate embedding from image description",
                "count": 0,
                "results": [],
            }

        from pgvector.django import CosineDistance

        qs = (
            AIDocumentEmbedding.objects
            .filter(document__source_type="product")
            .exclude(embedding__isnull=True)
            .annotate(distance=CosineDistance("embedding", query_embedding))
            .order_by("distance")[:top_k]
        )

        results = []
        for emb in qs.select_related("document"):
            doc = emb.document
            results.append({
                "document_id": str(doc.id),
                "source_id": doc.source_id,
                "source_type": doc.source_type,
                "score": round(1 - emb.distance, 4),
                "text_content": doc.text_content,
                "metadata": doc.metadata_json,
            })

        return {
            "tool": "ImageEmbeddingSearchTool",
            "count": len(results),
            "image_description": desc,
            "results": results,
        }
    except Exception as e:
        logger.exception("ImageEmbeddingSearchTool error")
        return {"tool": "ImageEmbeddingSearchTool", "error": str(e), "count": 0, "results": []}


def _describe_base64_image(ai: AIService, image_base64: str) -> str:
    """Send base64 image to Groq vision and return text description."""
    from ai_agentic_rag.config import VISION_MODEL

    completion = ai.groq_client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Describe this product image concisely for search purposes. "
                            "Include: product type, brand clues, color, size, visible features."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            }
        ],
        temperature=0.2,
        max_completion_tokens=200,
    )
    return completion.choices[0].message.content
