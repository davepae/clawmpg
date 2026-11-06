"""Coupon codes."""


class InvalidCoupon(ValueError):
    """Raised for unknown coupon codes."""


def redeem(code, amount):
    """Return ``amount`` after applying coupon ``code`` (case-insensitive)."""
    key = code.strip().upper()
    if key == "SAVE10":
        return amount * 0.9
    if key == "FLAT5":
        return max(0.0, amount - 5)
    raise InvalidCoupon(code)
