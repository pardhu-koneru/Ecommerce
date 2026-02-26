"""
SQLFilterTool — structured database queries against Product + ProductAttribute.

Returns structured JSON with matching products.
Supports filtering by: price range, brand, category, attributes, rating, stock.
"""
import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal

from django.db.models import Q, F

from products.models import Product, ProductAttribute
from categories.models import Category

logger = logging.getLogger(__name__)


def run(
    *,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    attributes: Optional[Dict[str, str]] = None,
    min_rating: Optional[float] = None,
    in_stock: Optional[bool] = None,
    order_by: str = "-rating_avg",
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Execute a SQL-backed product filter.

    Returns:
        {
            "tool": "SQLFilterTool",
            "count": int,
            "products": [{ id, title, brand, price, ... }]
        }
    """
    try:
        qs = Product.objects.filter(is_active=True)

        if min_price is not None:
            qs = qs.filter(price__gte=Decimal(str(min_price)))
        if max_price is not None:
            qs = qs.filter(price__lte=Decimal(str(max_price)))
        if brand:
            qs = qs.filter(brand__iexact=brand)
        if category:
            qs = qs.filter(
                Q(category__name__iexact=category)
                | Q(category__slug__iexact=category)
            )
        if min_rating is not None:
            qs = qs.filter(rating_avg__gte=min_rating)
        if in_stock is True:
            qs = qs.filter(stock_quantity__gt=0)
        if attributes:
            for key, value in attributes.items():
                qs = qs.filter(
                    attributes__key__iexact=key,
                    attributes__value__icontains=value,
                )

        allowed_orders = [
            "price", "-price", "rating_avg", "-rating_avg",
            "created_at", "-created_at", "title",
        ]
        if order_by not in allowed_orders:
            order_by = "-rating_avg"
        qs = qs.order_by(order_by)[:limit]

        products = []
        for p in qs.select_related("category").prefetch_related("attributes"):
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
            })

        return {
            "tool": "SQLFilterTool",
            "count": len(products),
            "products": products,
        }
    except Exception as e:
        logger.exception("SQLFilterTool error")
        return {"tool": "SQLFilterTool", "error": str(e), "count": 0, "products": []}
