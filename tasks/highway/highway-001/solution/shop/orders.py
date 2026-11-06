"""Order placement."""

from shop import config
from shop.pricing import apply_discount, bulk_discount, calc_total
from shop.tax import apply_tax


def place_order(items, discount_percent=0, bulk=False):
    """Price an order of (price, qty) pairs and return a summary dict."""
    subtotal = bulk_discount(items) if bulk else calc_total(items)
    discounted = apply_discount(subtotal, discount_percent) if discount_percent else subtotal
    total = apply_tax(discounted, config.TAX_RATE_PERCENT)
    return {"items": list(items), "subtotal": subtotal, "total": total}
