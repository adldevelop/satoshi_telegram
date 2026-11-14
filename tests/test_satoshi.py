# ==============================================================
# ✅ Teste automatizado - Satoshi Agent (pytest)
# ==============================================================
import asyncio
import pytest
from unittest.mock import MagicMock

from app.agent import (
    get_balances_margin,
    get_fibonacci_levels,
    calcular_preco_medio,
    get_margin_performance_30d,
    monitorar_mercado,
)

# ==============================================================
# 🔧 Mocks de dados da Binance
# ==============================================================


@pytest.fixture
def mock_binance_client(monkeypatch):
    """Mocka as respostas do client Binance utilizado no agent.py"""
    mock_client = MagicMock()

    # Mock saldo de conta margin
    mock_client.get_margin_account.return_value = {
        "userAssets": [
            {"asset": "BTC", "free": "0.00097902", "borrowed": "0.0", "interest": "0.0"},
            {"asset": "USDT", "free": "1000.0", "borrowed": "0.0", "interest": "0.0"},
        ],
        "totalNetAssetOfBtc": "0.00032",
        "totalAssetOfBtc": "0.00098",
    }

    # Mock preço BTCUSDT
    mock_client.get_symbol_ticker.return_value = {"symbol": "BTCUSDT", "price": "110000.00"}
    mock_client.ping.return_value = {}

    # Mock candles (para Fibonacci)
    candles = []
    for i in range(300):
        candles.append(["", "", "120000", "100000", "", ""])
    mock_client.get_klines.return_value = candles

    monkeypatch.setattr("app.agent.client", mock_client)
    return mock_client


# ==============================================================
# 🧪 Testes de funções principais
# ==============================================================


def test_get_balances_margin(mock_binance_client):
    """Valida leitura dos saldos margin (BTC e USDT)."""
    balances = get_balances_margin()
    assert balances is not None
    assert balances["BTC_free"] == pytest.approx(0.00097902)
    assert balances["USDT_borrowed"] == pytest.approx(0.0)
    assert balances["USDT_free"] == pytest.approx(1000.0)


def test_get_fibonacci_levels(mock_binance_client):
    """Valida cálculo dos níveis de Fibonacci a partir dos candles mockados."""
    levels = get_fibonacci_levels("BTCUSDT")
    retracoes = levels["retracoes"]
    assert "0.382" in retracoes
    assert retracoes["0.382"] == pytest.approx(107640.0)  # 100k + (20k * 0.382)
    assert levels["high"] == 120000
    assert levels["low"] == 100000


def test_calcular_preco_medio():
    """Valida o cálculo do preço médio de compra baseado em múltiplas entradas."""
    entries = [
        {"price": 100.0},
        {"price": 200.0},
        {"price": 300.0},
    ]
    preco_medio = calcular_preco_medio(entries)
    assert preco_medio == pytest.approx(200.0)


def test_get_margin_performance_30d(tmp_path, monkeypatch, mock_binance_client):
    """Valida cálculo de collateral, ROI e PnL."""
    fake_pnl_path = tmp_path / "pnl_history.json"
    monkeypatch.setattr("app.agent.PNL_HISTORY_FILE", str(fake_pnl_path))

    account_data = mock_binance_client.get_margin_account()
    perf = get_margin_performance_30d(account_data)

    assert "collateral_usdt" in perf
    assert "roi_pct" in perf
    assert isinstance(perf["collateral_usdt"], float)
    assert isinstance(perf["roi_pct"], float)


# ==============================================================
# 🎯 Estratégia híbrida — simula um ciclo com sinal e ordem
# ==============================================================


@pytest.mark.asyncio
async def test_execucao_entrada_hibrida(monkeypatch, mock_binance_client):
    import app.agent as agent_mod
    from app.strategy.hybrid import HybridSignal

    def fake_hybrid(*_a, **_k):
        return HybridSignal(True, "teste", {"trend_ok": True})

    def fake_order_safe(*_a, **_k):
        return {
            "ok": True,
            "mode": "real",
            "quantity": 0.01,
            "price": 107650.0,
            "usdt": 250.0,
        }

    def fake_pos(_c, st, _p, _sym, _mode, sl_pct=0.025, **kw):
        return st, [], None, None

    base_state = {
        "last_entry_cycle": None,
        "entries": [],
        "last_price": None,
        "trades_today_count": 0,
        "trades_day_key": None,
        "open_position": None,
        "consecutive_losses": 0,
        "consecutive_api_errors": 0,
        "trading_paused": False,
        "pause_reason": None,
    }

    def fake_load():
        return base_state

    def fake_get_market_data(_sym):
        return {"symbol": "BTCUSDT", "price": 107650.0}

    monkeypatch.setattr(agent_mod, "evaluate_hybrid_entry", fake_hybrid)
    monkeypatch.setattr(agent_mod, "create_order_safe", fake_order_safe)
    monkeypatch.setattr(agent_mod, "process_open_position", fake_pos)
    monkeypatch.setattr(agent_mod, "load_state", fake_load)
    monkeypatch.setattr(agent_mod, "save_state", lambda _s: None)
    monkeypatch.setattr(agent_mod, "salvar_log", lambda *a, **kw: None)
    monkeypatch.setattr(agent_mod, "send_telegram_message", lambda *a, **kw: None)
    monkeypatch.setattr(agent_mod, "get_market_data", fake_get_market_data)

    async def fake_sleep(_s):
        raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await monitorar_mercado(intervalo_segundos=1)

    assert base_state.get("open_position") is not None
    assert base_state.get("trades_today_count", 0) >= 1


# ==============================================================
# 🧱 Teste de integração final (mock geral)
# ==============================================================


def test_integracao_geral(mock_binance_client):
    """Valida integração geral das funções de alto nível."""
    balances = get_balances_margin()
    fib = get_fibonacci_levels()
    perf = get_margin_performance_30d(mock_binance_client.get_margin_account())

    assert balances and "BTC_free" in balances
    assert "retracoes" in fib
    assert "roi_pct" in perf
    assert perf["collateral_usdt"] > 0
