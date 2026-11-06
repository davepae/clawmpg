"""Reporting helpers."""

from shop.pricing import calc_total


def line_summary(items):
    """Summarise the lines of an order."""
    return {"lines": len(items), "gross": calc_total(items)}


def daily_summary(orders):
    """Summarise a list of placed orders."""
    return {"orders": len(orders), "revenue": round(sum(o["total"] for o in orders), 2)}
