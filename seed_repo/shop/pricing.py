"""Pricing helpers."""


def calc_total(items):
    """Sum price * qty for (price, qty) pairs."""
    return sum(price * qty for price, qty in items)


def apply_discount(price, percent):
    """Return ``price`` after a percentage discount (percent is 0-100)."""
    return price - percent
