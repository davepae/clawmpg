from shop.orders import place_order
from shop.reports import line_summary


def test_place_order_subtotal():
    order = place_order([(10.0, 2)])
    assert order["subtotal"] == 20.0
    assert order["items"] == [(10.0, 2)]


def test_line_summary():
    assert line_summary([(10.0, 2)]) == {"lines": 1, "gross": 20.0}
