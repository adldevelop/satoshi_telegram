# ==============================================================
# 📊 Tool: get_account_status_tool — status consolidado da conta Margin BTCUSDT
# ==============================================================

import os
import json
from datetime import datetime
from typing import Dict, Any
from binance.client import Client

LOG_DIR = "logs"
STATE_FILE = os.path.join(LOG_DIR, "state.json")

BNB_API_KEY = os.getenv("BNB_API_KEY")
BNB_API_SECRET = os.getenv("BNB_API_SECRET")
LEVERAGE = int(os.getenv("LEVERAGE", "5"))

_client = Client(api_key=BNB_API_KEY, api_secret=BNB_API_SECRET)


def _get_btc_price() -> float:
    """Obtém o preço atual do BTC/USDT"""
    try:
        ticker = _client.get_symbol_ticker(symbol="BTCUSDT")
        return float(ticker["price"])
    except Exception:
        return 0.0


def _get_margin_balances() -> Dict[str, float]:
    """Obtém os saldos margin da conta (BTC e USDT)"""
    try:
        acc = _client.get_margin_account()
        assets = {a["asset"]: a for a in acc["userAssets"]}

        def _parse(v): return float(v) if v else 0.0

        btc = assets.get("BTC", {})
        usdt = assets.get("USDT", {})

        return {
            "BTC_free": _parse(btc.get("free")),
            "BTC_borrowed": _parse(btc.get("borrowed")),
            "USDT_free": _parse(usdt.get("free")),
            "USDT_borrowed": _parse(usdt.get("borrowed")),
            "totalAssetOfBtc": float(acc.get("totalAssetOfBtc", 0.0)),
            "totalNetAssetOfBtc": float(acc.get("totalNetAssetOfBtc", 0.0)),
        }
    except Exception:
        return {}


def _load_state() -> Dict[str, Any]:
    """Lê histórico local de entradas"""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"entries": []}


def get_account_status_tool(symbol: str = "BTCUSDT") -> Dict[str, Any]:
    """
    Retorna status consolidado da conta Margin:
    - preço atual
    - saldos (BTC e USDT)
    - total alavancado e alavancagem observada
    - preço médio de compra
    """
    price = _get_btc_price()
    balances = _get_margin_balances()

    if not balances:
        return {"error": "Não foi possível obter dados da conta margin."}

    total_alavancado = balances.get("totalAssetOfBtc", 0.0) * price
    usdt_free = balances.get("USDT_free", 0.0)
    effective_leverage = round(total_alavancado / max(usdt_free, 1e-9), 2) if usdt_free > 0 else None

    state = _load_state()
    entries = state.get("entries", [])
    preco_medio = (
        round(sum(e["price"] for e in entries) / len(entries), 2) if entries else None
    )

    return {
        "symbol": symbol,
        "price_now": price,
        "BTC_free": balances["BTC_free"],
        "USDT_free": balances["USDT_free"],
        "total_alavancado_usd": round(total_alavancado, 2),
        "configured_leverage": LEVERAGE,
        "observed_leverage": effective_leverage,
        "entries_count": len(entries),
        "preco_medio": preco_medio,
        "timestamp": datetime.utcnow().isoformat(),
    }
