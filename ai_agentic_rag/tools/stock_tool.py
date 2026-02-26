"""
StockCheckTool — lightweight inventory availability check.

SQL only, no embeddings.
"""
import logging
from typing import Dict, Any, Optional, List

from products.models import Product

logger = logging.getLogger(__name__)


def run(
    *,
    product_ids: Optional[List[str]] = None,
    title_contains: Optional[str] = None,
    brand: Optional[str] = None,
    only_in_stock: bool = False,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Check stock availability for products.

    Provide product_ids for direct lookup, or title_contains/brand for search.

    Returns:
        {
            "tool": "StockCheckTool",
            "count": int,
            "products": [{ id, title, brand, stock_quantity, in_stock }]
        }
    """
    try:
        qs = Product.objects.filter(is_active=True)

        if product_ids:
            qs = qs.filter(id__in=product_ids)
        if title_contains:
            qs = qs.filter(title__icontains=title_contains)
        if brand:
            qs = qs.filter(brand__iexact=brand)
        if only_in_stock:
            qs = qs.filter(stock_quantity__gt=0)

        qs = qs.order_by("-stock_quantity")[:limit]

        products = []
        for p in qs:
            products.append({
                "id": str(p.id),
                "title": p.title,
                "brand": p.brand or "",
                "price": float(p.price),
                "stock_quantity": p.stock_quantity,
                "in_stock": p.stock_quantity > 0,
            })

        return {
            "tool": "StockCheckTool",
            "count": len(products),
            "products": products,
        }
    except Exception as e:
        logger.exception("StockCheckTool error")
        return {"tool": "StockCheckTool", "error": str(e), "count": 0, "products": []}
