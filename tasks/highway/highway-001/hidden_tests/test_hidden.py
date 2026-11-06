from shop.orders import place_order
from shop.pricing import bulk_discount


def test_bulk_applies_at_threshold():
    assert bulk_discount([(100.0, 10)]) == 950.0


def test_bulk_not_applied_below_threshold():
    assert bulk_discount([(10.0, 9)]) == 90.0


def test_bulk_counts_quantity_across_items():
    assert bulk_discount([(10.0, 6), (20.0, 4)]) == 133.0


def test_bulk_custom_params():
    assert bulk_discount([(10.0, 2)], min_qty=2, percent=50) == 10.0


def test_place_order_bulk_flag():
    assert place_order([(10.0, 10)], bulk=True)["subtotal"] == 95.0
    assert place_order([(10.0, 10)])["subtotal"] == 100.0
