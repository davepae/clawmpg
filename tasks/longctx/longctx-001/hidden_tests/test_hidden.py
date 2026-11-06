from shop.orders import place_order
from shop.tax import apply_tax


def test_order_total_with_tax():
    assert place_order([(10.0, 2)])["total"] == 21.6


def test_tax_contract_unchanged():
    assert apply_tax(100, 0.08) == 108.0


def test_empty_order():
    assert place_order([])["total"] == 0.0
