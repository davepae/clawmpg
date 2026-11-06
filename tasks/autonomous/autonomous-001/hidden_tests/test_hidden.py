import pytest

from shop.coupons import InvalidCoupon, redeem
from shop.orders import place_order


def test_percent_coupon_case_insensitive():
    assert redeem("save10", 200) == 180.0


def test_flat_coupon_floor():
    assert redeem("FLAT5", 20) == 15.0
    assert redeem("FLAT5", 3) == 0.0


def test_invalid_coupon():
    assert issubclass(InvalidCoupon, ValueError)
    with pytest.raises(InvalidCoupon):
        redeem("BOGUS", 10)


def test_place_order_net_and_coupon_key():
    plain = place_order([(10.0, 2)])
    assert plain["net"] == 20.0
    assert "coupon" not in plain
    order = place_order([(10.0, 2)], coupon="SAVE10")
    assert order["net"] == 18.0
    assert order["coupon"] == "SAVE10"


def test_order_of_operations():
    order = place_order([(10.0, 2)], discount_percent=10, coupon="FLAT5")
    assert order["net"] == 13.0


def test_invalid_coupon_in_order():
    with pytest.raises(InvalidCoupon):
        place_order([(10.0, 2)], coupon="NOPE")
