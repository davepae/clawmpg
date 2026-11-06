"""Tax helpers."""


def apply_tax(amount, rate):
    """Return ``amount`` with tax added. ``rate`` is a fraction, e.g. 0.08."""
    return round(amount * (1 + rate), 2)
