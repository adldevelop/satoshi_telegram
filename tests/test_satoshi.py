import asyncio
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.agent import (
    calcular_preco_medio,
    get_balances_margin,
    get_fibonacci_levels,
    get_margin_performance_30d,
    monitorar_mercado,
)


@pytest.fixture
def mock_binance_client(monkeypatch):
    import app.agent as agent_mod

    mock_client = MagicMock()
    mock_client.get_margin_account.return_value = {
        "userAssets": [
            {"asset": "BTC", "free": "0.00097902", "borrowed": "0.0", "interest": "0.0"},
            {"asset": "USDT", "free": "1000.0", "borrowed": "0.0", "interest": "0.0"},
        ],
        "totalNetAssetOfBtc": "0.00032",
        "totalAssetOfBtc": "0.00098",
    }
    mock_client.get_symbol_ticker.return_value = {"symbol": "BTCUSDT", "price": "110000.00"}
    mock_client.get_klines.return_value = [["", "", "120000", "100000", "", ""] for _ in range(180)]
    monkeypatch.setattr(agent_mod, "client", mock_client)
    return mock_client


def test_importing_app_package_does_not_load_trader_or_adk():
    workspace = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, app; assert 'app.agent' not in sys.modules; "
            "import app.agent; assert 'google.adk.agents' not in sys.modules",
        ],
        cwd=workspace,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_get_balances_margin(mock_binance_client):
    balances = get_balances_margin()

    assert balances is not None
    assert balances["BTC_free"] == pytest.approx(0.00097902)
    assert balances["USDT_borrowed"] == pytest.approx(0.0)
    assert balances["USDT_free"] == pytest.approx(1000.0)


def test_get_fibonacci_levels(mock_binance_client):
    levels = get_fibonacci_levels("BTCUSDT")

    assert levels["retracoes"]["0.382"] == pytest.approx(107640.0)
    assert levels["high"] == 120000
    assert levels["low"] == 100000
    mock_binance_client.get_klines.assert_called_once_with(
        symbol="BTCUSDT",
        interval="4h",
        limit=180,
    )


def test_calcular_preco_medio():
    assert calcular_preco_medio([{"price": 100.0}, {"price": 200.0}, {"price": 300.0}]) == 200.0
    assert calcular_preco_medio([]) is None


def test_margin_performance_reuses_market_price(tmp_path, monkeypatch, mock_binance_client):
    import app.agent as agent_mod

    history_path = tmp_path / "pnl_history.json"
    monkeypatch.setattr(agent_mod, "PNL_HISTORY_FILE", str(history_path))
    monkeypatch.setattr(agent_mod, "get_btc_price", lambda: pytest.fail("unexpected price request"))

    result = get_margin_performance_30d(
        mock_binance_client.get_margin_account(),
        btc_price=100_000,
    )

    assert result["collateral_usdt"] == 32.0
    assert isinstance(result["roi_pct"], float)


@pytest.mark.asyncio
async def test_cycle_reuses_account_response_and_simulates_entry(
    tmp_path,
    monkeypatch,
    mock_binance_client,
):
    import app.agent as agent_mod

    state = {"last_entry_cycle": None, "entries": [], "last_price": None}
    saved_states = []
    logged_cycles = []
    monkeypatch.setattr(agent_mod, "TRADING_MODE", "dry")
    monkeypatch.setattr(agent_mod, "PNL_HISTORY_FILE", str(tmp_path / "pnl_history.json"))
    monkeypatch.setattr(agent_mod, "load_state", lambda: state)
    monkeypatch.setattr(agent_mod, "save_state", saved_states.append)
    monkeypatch.setattr(agent_mod, "salvar_log", lambda *args, **kwargs: logged_cycles.append(args))
    monkeypatch.setattr(agent_mod, "send_telegram_message", lambda _message: None)
    monkeypatch.setattr(agent_mod, "get_market_data", lambda _symbol: {"price": 107000.0})
    monkeypatch.setattr(agent_mod, "ultima_zona_fibo", None)
    monkeypatch.setattr(agent_mod, "zona_executada", False)
    monkeypatch.setattr(agent_mod, "ultimo_preco", None)

    async def cancel_after_cycle(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", cancel_after_cycle)

    with pytest.raises(asyncio.CancelledError):
        await monitorar_mercado(intervalo_segundos=1)

    mock_binance_client.get_margin_account.assert_called_once()
    assert len(state["entries"]) == 1
    assert state["entries"][0]["price"] == 107000.0
    assert saved_states[0]["entries"] == state["entries"]
    assert logged_cycles[0][3] == "Análise determinística: preço 107000.00, zona [106563.60 — 107640.00]."
