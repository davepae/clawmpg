"""Pricing helpers."""


def calc_total(items):
    """Sum price * qty for (price, qty) pairs."""
    return sum(price * qty for price, qty in items)


def apply_discount(price, percent):
    """Return ``price`` after a percentage discount (percent is 0-100)."""
    return price * (1 - percent / 100)


def bulk_discount(items, min_qty=10, percent=5):
    """Total of ``items``, discounted by ``percent`` if quantity >= ``min_qty``."""
    total = calc_total(items)
    if sum(qty for _, qty in items) >= min_qty:
        return apply_discount(total, percent)
    return total
