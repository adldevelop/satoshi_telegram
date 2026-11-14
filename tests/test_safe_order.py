from unittest.mock import MagicMock
from app.execution.safe_order import (
    floor_to_step,
    usdt_to_quantity_btc,
    get_lot_size_rules,
    LotRules,
)


def test_floor_to_step_btc():
    assert floor_to_step(0.001234, 0.00001) == 0.00123
    assert floor_to_step(0.0, 0.00001) == 0.0


def test_usdt_to_qty_min_notional():
    rules = LotRules(
        min_qty=0.00001,
        max_qty=1e9,
        step_size=0.00001,
        min_notional=10.0,
    )
    q, err = usdt_to_quantity_btc(250.0, 100000.0, rules)
    assert err == "" and q > 0
    assert q * 100000.0 >= 10.0


def test_get_lot_size_rules_mock():
    c = MagicMock()
    c.get_symbol_info.return_value = {
        "symbol": "BTCUSDT",
        "filters": [
            {
                "filterType": "LOT_SIZE",
                "minQty": "0.00001000",
                "maxQty": "9000.00000000",
                "stepSize": "0.00001000",
            },
            {"filterType": "NOTIONAL", "minNotional": "5.0"},
        ],
    }
    r = get_lot_size_rules(c, "BTCUSDT")
    assert r.step_size == 0.00001
    assert r.min_notional == 5.0
