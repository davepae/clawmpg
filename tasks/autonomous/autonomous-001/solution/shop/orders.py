"""Order placement."""

from shop import config
from shop.coupons import redeem
from shop.pricing import apply_discount, calc_total
from shop.tax import apply_tax


def place_order(items, discount_percent=0, coupon=None):
    """Price an order of (price, qty) pairs and return a summary dict."""
    subtotal = calc_total(items)
    net = apply_discount(subtotal, discount_percent) if discount_percent else subtotal
    if coupon is not None:
        net = redeem(coupon, net)
    total = apply_tax(net, config.TAX_RATE_PERCENT / 100)
    order = {"items": list(items), "subtotal": subtotal, "net": net, "total": total}
    if coupon is not None:
        order["coupon"] = coupon
    return order
