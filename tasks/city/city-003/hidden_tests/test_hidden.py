import logging

from shop.orders import place_order


def test_logs_order(caplog):
    with caplog.at_level(logging.INFO, logger="shop.orders"):
        place_order([(10.0, 2), (5.0, 1)])
    msgs = [r.getMessage() for r in caplog.records if r.name == "shop.orders"]
    assert len(msgs) == 1
    assert "items=2" in msgs[0]
    assert "subtotal=25.0" in msgs[0]
    assert caplog.records[0].levelno == logging.INFO
