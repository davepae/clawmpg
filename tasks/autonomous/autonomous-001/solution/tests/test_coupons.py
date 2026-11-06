import pytest

from shop.coupons import InvalidCoupon, redeem
from shop.orders import place_order


def test_redeem_percent():
    assert redeem("SAVE10", 100) == 90.0


def test_redeem_invalid():
    with pytest.raises(InvalidCoupon):
        redeem("X", 1)


def test_order_with_coupon():
    assert place_order([(10.0, 2)], coupon="FLAT5")["net"] == 15.0
