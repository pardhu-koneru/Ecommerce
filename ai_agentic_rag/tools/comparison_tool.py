"""
ComparisonTool — multi-product structured comparison.

Fetches full details (attributes, ratings, price, stock, review summary)
for 2+ products and structures them side-by-side.

Accepts either valid UUIDs or product names/keywords. When non-UUID
strings are provided (e.g. "iPhone 14"), the tool resolves them to
products via title search.
"""
import logging
import uuid as _uuid
from typing import Dict, Any, List, Optional

from django.db.models import Q

from products.models import Product
from reviews.models import ReviewEmbedding

logger = logging.getLogger(__name__)


def _is_valid_uuid(val: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        _uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False


def _resolve_product_ids(identifiers: List[str]) -> List[str]:
    """
    Resolve a list of identifiers (UUIDs or product names/keywords)
    to actual product UUIDs.

    - Valid UUIDs are kept as-is (if they exist in DB).
    - Non-UUID strings are treated as title search keywords.
      The best-matching active product per keyword is returned.
    """
    resolved_ids: List[str] = []
    seen = set()

    for ident in identifiers:
        if _is_valid_uuid(ident):
            if ident not in seen:
                resolved_ids.append(ident)
                seen.add(ident)
        else:
            # Title-based lookup: find the closest matching product
            matches = (
                Product.objects
                .filter(is_active=True, title__icontains=ident)
                .order_by("-rating_avg")
                .values_list("id", flat=True)[:1]
            )
            for pid in matches:
                pid_str = str(pid)
                if pid_str not in seen:
                    resolved_ids.append(pid_str)
                    seen.add(pid_str)
                    logger.info(f"ComparisonTool resolved '{ident}' -> {pid_str}")

            if not matches:
                logger.warning(f"ComparisonTool: no product found for '{ident}'")

    return resolved_ids


def run(
    *,
    product_ids: List[str],
) -> Dict[str, Any]:
    """
    Build a structured comparison table for the given product identifiers.

    Accepts UUIDs or product names. Non-UUID strings are automatically
    resolved to products via title search.

    Returns:
        {
            "tool": "ComparisonTool",
            "count": int,
            "products": [ ... ]
        }
    """
    try:
        if not product_ids or len(product_ids) < 2:
            return {
                "tool": "ComparisonTool",
                "error": "At least 2 product IDs required for comparison",
                "count": 0,
                "products": [],
            }

        # Resolve any non-UUID identifiers (product names) to real UUIDs
        resolved = _resolve_product_ids(product_ids)

        if len(resolved) < 2:
            return {
                "tool": "ComparisonTool",
                "error": f"Could not resolve enough products for comparison. Identifiers given: {product_ids}",
                "count": 0,
                "products": [],
            }

        qs = (
            Product.objects
            .filter(id__in=resolved, is_active=True)
            .select_related("category")
            .prefetch_related("attributes")
        )

        # pre-fetch review summaries
        review_map: Dict[str, str] = {}
        for re in ReviewEmbedding.objects.filter(product_id__in=resolved):
            review_map[str(re.product_id)] = re.summary

        products = []
        for p in qs:
            attrs = {a.key: a.value for a in p.attributes.all()}
            products.append({
                "id": str(p.id),
                "title": p.title,
                "brand": p.brand or "",
                "category": p.category.name,
                "price": float(p.price),
                "currency": p.currency,
                "stock_quantity": p.stock_quantity,
                "rating_avg": p.rating_avg,
                "rating_count": p.rating_count,
                "attributes": attrs,
                "review_summary": review_map.get(str(p.id), "No review summary available"),
            })

        return {
            "tool": "ComparisonTool",
            "count": len(products),
            "products": products,
        }
    except Exception as e:
        logger.exception("ComparisonTool error")
        return {"tool": "ComparisonTool", "error": str(e), "count": 0, "products": []}
