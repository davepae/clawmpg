from shop.pricing import apply_discount, calc_total


def test_calc_total():
    assert calc_total([(2.0, 3), (1.5, 2)]) == 9.0


def test_apply_discount():
    assert apply_discount(200, 10) == 180
