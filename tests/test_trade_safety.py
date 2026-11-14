from unittest.mock import MagicMock

import pytest

from app.config import get_buy_percent, get_trading_mode


@pytest.mark.parametrize("mode", ["", "production", "true", "dr"])
def test_invalid_trading_mode_is_rejected(monkeypatch, mode):
    monkeypatch.setenv("TRADING_MODE", mode)

    with pytest.raises(ValueError, match="TRADING_MODE"):
        get_trading_mode()


@pytest.mark.parametrize("percent", ["0", "-0.1", "1.01", "not-a-number"])
def test_invalid_buy_percent_is_rejected(monkeypatch, percent):
    monkeypatch.setenv("BUY_PERCENT", percent)

    with pytest.raises(ValueError, match="BUY_PERCENT"):
        get_buy_percent()


def test_buy_percent_reads_configured_fraction(monkeypatch):
    monkeypatch.setenv("BUY_PERCENT", "0.25")

    assert get_buy_percent() == 0.25


def test_sell_requires_explicit_percent_and_does_not_query_exchange(monkeypatch):
    import app.tools.sell_market as sell_mod

    client = MagicMock()
    monkeypatch.setattr(sell_mod, "_client", client)

    result = sell_mod.sell_market_tool()

    assert result["ok"] is False
    client.get_margin_account.assert_not_called()


def test_real_sell_requires_confirmation_before_exchange(monkeypatch):
    import app.tools.sell_market as sell_mod

    client = MagicMock()
    monkeypatch.setattr(sell_mod, "_client", client)
    monkeypatch.setattr(sell_mod, "TRADING_MODE", "real")

    result = sell_mod.sell_market_tool(percent=10)

    assert result["ok"] is False
    assert "Confirmação" in result["error"]
    client.get_margin_account.assert_not_called()


def test_real_sell_does_not_accept_truthy_non_boolean_confirmation(monkeypatch):
    import app.tools.sell_market as sell_mod

    client = MagicMock()
    monkeypatch.setattr(sell_mod, "_client", client)
    monkeypatch.setattr(sell_mod, "TRADING_MODE", "real")

    result = sell_mod.sell_market_tool(percent=10, confirmed="true")

    assert result["ok"] is False
    client.get_margin_account.assert_not_called()


@pytest.mark.parametrize("percent", [0, 0.5, 40.1, float("nan"), "invalid"])
def test_sell_rejects_invalid_percent_before_exchange(monkeypatch, percent):
    import app.tools.sell_market as sell_mod

    client = MagicMock()
    monkeypatch.setattr(sell_mod, "_client", client)

    result = sell_mod.sell_market_tool(percent=percent)

    assert result["ok"] is False
    client.get_margin_account.assert_not_called()


def test_sell_caps_quantity_to_requested_share_of_free_btc(monkeypatch):
    import app.tools.sell_market as sell_mod

    client = MagicMock()
    client.get_margin_account.return_value = {
        "userAssets": [{"asset": "BTC", "free": "0.123456", "borrowed": "1.0"}]
    }
    client.create_margin_order.return_value = {
        "orderId": 123,
        "status": "FILLED",
        "executedQty": "0.04938",
        "cummulativeQuoteQty": "4938",
    }
    monkeypatch.setattr(sell_mod, "_client", client)
    monkeypatch.setattr(sell_mod, "_get_price", lambda _symbol: 100_000.0)
    monkeypatch.setattr(sell_mod, "_get_filters", lambda _symbol: (0.00001, 0.00001))
    monkeypatch.setattr(sell_mod, "TRADING_MODE", "real")

    result = sell_mod.sell_market_tool(percent=40, confirmed=True)

    assert result["ok"] is True
    assert result["percent_basis"] == "free_btc_balance"
    assert result["qty_btc"] == pytest.approx(0.04938)
    assert result["qty_btc"] <= 0.123456 * 0.40
    client.create_margin_order.assert_called_once_with(
        symbol="BTCUSDT",
        side="SELL",
        type="MARKET",
        quantity=pytest.approx(0.04938),
        sideEffectType="AUTO_REPAY",
    )


def test_sell_does_not_report_success_without_exchange_fill(monkeypatch):
    import app.tools.sell_market as sell_mod

    client = MagicMock()
    client.get_margin_account.return_value = {
        "userAssets": [{"asset": "BTC", "free": "0.123456"}]
    }
    client.create_margin_order.return_value = {
        "orderId": 789,
        "status": "REJECTED",
        "executedQty": "0",
    }
    monkeypatch.setattr(sell_mod, "_client", client)
    monkeypatch.setattr(sell_mod, "_get_price", lambda _symbol: 100_000.0)
    monkeypatch.setattr(sell_mod, "_get_filters", lambda _symbol: (0.00001, 0.00001))
    monkeypatch.setattr(sell_mod, "TRADING_MODE", "real")

    result = sell_mod.sell_market_tool(percent=10, confirmed=True)

    assert result["ok"] is False
    assert "não confirmou execução" in result["error"]


def test_sell_does_not_round_up_to_minimum_lot(monkeypatch):
    import app.tools.sell_market as sell_mod

    client = MagicMock()
    client.get_margin_account.return_value = {
        "userAssets": [{"asset": "BTC", "free": "0.0005"}]
    }
    monkeypatch.setattr(sell_mod, "_client", client)
    monkeypatch.setattr(sell_mod, "_get_price", lambda _symbol: 100_000.0)
    monkeypatch.setattr(sell_mod, "_get_filters", lambda _symbol: (0.0003, 0.0001))
    monkeypatch.setattr(sell_mod, "TRADING_MODE", "real")

    result = sell_mod.sell_market_tool(percent=40, confirmed=True)

    assert result["ok"] is False
    client.create_margin_order.assert_not_called()


def test_legacy_order_helper_never_posts_in_dry_mode(monkeypatch):
    import app.tools.create_order as order_mod

    monkeypatch.setenv("TRADING_MODE", "dry")
    monkeypatch.setattr(order_mod.requests, "post", MagicMock())
    monkeypatch.setattr(order_mod, "BNB_API_KEY", "test-key")
    monkeypatch.setattr(order_mod, "BNB_API_SECRET", "test-secret")

    result = order_mod.create_margin_order("BTCUSDT", "BUY", 0.01)

    assert result is None
    order_mod.requests.post.assert_not_called()


def test_legacy_order_tool_rejects_invalid_mode_before_network(monkeypatch):
    import app.tools.create_order as order_mod

    monkeypatch.setenv("TRADING_MODE", "prod")
    get_balance = MagicMock(return_value=1000.0)
    monkeypatch.setattr(order_mod, "get_margin_account_balance", get_balance)

    result = order_mod.create_order_tool()

    assert result["status"] == "ERROR"
    get_balance.assert_not_called()


def test_legacy_buy_uses_buy_percent_in_real_mode(monkeypatch):
    import app.tools.create_order as order_mod

    monkeypatch.setenv("TRADING_MODE", "real")
    monkeypatch.setenv("BUY_PERCENT", "0.25")
    monkeypatch.setattr(order_mod, "BNB_API_KEY", "test-key")
    monkeypatch.setattr(order_mod, "BNB_API_SECRET", "test-secret")
    monkeypatch.setattr(order_mod, "get_margin_account_balance", lambda _asset: 1000.0)
    monkeypatch.setattr(order_mod, "get_ticker_price", lambda _symbol: 100_000.0)
    submit_order = MagicMock(
        return_value={"orderId": 456, "status": "FILLED", "executedQty": "0.005"}
    )
    monkeypatch.setattr(order_mod, "create_margin_order", submit_order)

    result = order_mod.create_order_tool(leverage=2)

    assert result["status"] == "ORDER_EXECUTED"
    assert result["quantity"] == pytest.approx(0.005)
    assert result["capital_used_usdt"] == 250.0
    submit_order.assert_called_once_with("BTCUSDT", "BUY", pytest.approx(0.005))