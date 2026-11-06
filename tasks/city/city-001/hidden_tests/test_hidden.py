from shop.pricing import apply_discount


def test_discount_basic():
    assert apply_discount(200, 10) == 180


def test_discount_zero():
    assert apply_discount(50, 0) == 50


def test_discount_quarter():
    assert apply_discount(80, 25) == 60
