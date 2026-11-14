import json
from unittest.mock import MagicMock

import pytest

from app.agent import (
    _rotate_log_file,
    get_balances_margin,
    get_margin_performance_30d,
)


def test_get_balances_uses_supplied_account_without_network_call(monkeypatch):
    import app.agent as agent_mod

    account_data = {
        "userAssets": [
            {"asset": "BTC", "free": "0.01", "borrowed": "0", "interest": "0"},
            {"asset": "USDT", "free": "250", "borrowed": "0", "interest": "0"},
        ]
    }
    client = MagicMock()
    monkeypatch.setattr(agent_mod, "client", client)

    balances = get_balances_margin(account_data)

    assert balances["BTC_free"] == 0.01
    assert balances["USDT_free"] == 250
    client.get_margin_account.assert_not_called()


def test_margin_performance_uses_supplied_price(tmp_path, monkeypatch):
    import app.agent as agent_mod

    history_path = tmp_path / "pnl_history.json"
    monkeypatch.setattr(agent_mod, "PNL_HISTORY_FILE", str(history_path))
    monkeypatch.setattr(agent_mod, "get_btc_price", lambda: pytest.fail("unexpected network price call"))

    result = get_margin_performance_30d({"totalNetAssetOfBtc": "0.01"}, btc_price=100_000)

    assert result["collateral_usdt"] == 1000
    assert json.loads(history_path.read_text())[0]["collateral_usdt"] == 1000


def test_rotate_log_file_keeps_only_configured_backups(tmp_path):
    log_path = tmp_path / "agent.jsonl"
    log_path.write_text("current log is large")
    (tmp_path / "agent.jsonl.1").write_text("previous log")

    _rotate_log_file(str(log_path), max_bytes=1, backup_count=1)

    assert not log_path.exists()
    assert (tmp_path / "agent.jsonl.1").read_text() == "current log is large"


def test_market_data_reuses_binance_client(monkeypatch):
    import app.tools.get_market_data as market_data_mod

    client = MagicMock()
    client.get_ticker.return_value = {
        "lastPrice": "100000",
        "highPrice": "101000",
        "lowPrice": "99000",
        "volume": "12",
        "closeTime": 123,
    }
    monkeypatch.setattr(market_data_mod, "client", client)
    monkeypatch.setattr(market_data_mod, "Client", MagicMock(side_effect=AssertionError("client recreated")))

    first_result = market_data_mod.get_market_data("BTCUSDT")
    second_result = market_data_mod.get_market_data("BTCUSDT")

    assert first_result["price"] == second_result["price"] == 100000
    assert client.get_ticker.call_count == 2