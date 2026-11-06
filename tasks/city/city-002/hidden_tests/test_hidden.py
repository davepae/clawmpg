from shop import pricing
from shop.orders import place_order
from shop.pricing import compute_total
from shop.reports import line_summary


def test_compute_total():
    assert compute_total([(2.0, 3)]) == 6.0


def test_old_name_gone():
    assert not hasattr(pricing, "calc_total")


def test_callers_updated():
    assert place_order([(10.0, 2)])["subtotal"] == 20.0
    assert line_summary([(10.0, 2)]) == {"lines": 1, "gross": 20.0}
