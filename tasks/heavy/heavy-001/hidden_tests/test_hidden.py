import importlib.util

from shop.billing import pricing, tax
from shop.orders import place_order
from shop.reports import line_summary


def test_new_locations():
    assert pricing.calc_total([(2.0, 3)]) == 6.0
    assert tax.apply_tax(100, 0.08) == 108.0


def test_old_modules_gone():
    assert importlib.util.find_spec("shop.pricing") is None
    assert importlib.util.find_spec("shop.tax") is None


def test_callers_still_work():
    assert place_order([(10.0, 2)])["subtotal"] == 20.0
    assert line_summary([(10.0, 2)]) == {"lines": 1, "gross": 20.0}
