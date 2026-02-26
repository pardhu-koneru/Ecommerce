"""
ComparisonTool — multi-product structured comparison.

Fetches full details (attributes, ratings, price, stock, review summary)
for 2+ products and structures them side-by-side.
"""
import logging
from typing import Dict, Any, List, Optional

from products.models import Product
from reviews.models import ReviewEmbedding

logger = logging.getLogger(__name__)


def run(
    *,
    product_ids: List[str],
) -> Dict[str, Any]:
    """
    Build a structured comparison table for the given product IDs.

    Returns:
        {
            "tool": "ComparisonTool",
            "count": int,
            "products": [
                {
                    id, title, brand, category, price, stock_quantity,
                    rating_avg, rating_count, attributes: {}, review_summary
                }
            ]
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

        qs = (
            Product.objects
            .filter(id__in=product_ids, is_active=True)
            .select_related("category")
            .prefetch_related("attributes")
        )

        # pre-fetch review summaries
        review_map: Dict[str, str] = {}
        for re in ReviewEmbedding.objects.filter(product_id__in=product_ids):
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
