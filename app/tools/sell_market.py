# ==============================================================
# 💰 Tool: sell_market_tool — venda parcial de BTCUSDT (1%–40%)
# ==============================================================

import os
from decimal import Decimal
from typing import Dict, Any, Optional
from binance.client import Client
from binance.exceptions import BinanceAPIException

BNB_API_KEY = os.getenv("BNB_API_KEY")
BNB_API_SECRET = os.getenv("BNB_API_SECRET")
TRADING_MODE = os.getenv("TRADING_MODE", "dry").lower().strip()  # "dry" ou "real"

_client = Client(api_key=BNB_API_KEY, api_secret=BNB_API_SECRET)


def _get_price(symbol="BTCUSDT") -> float:
    try:
        return float(_client.get_symbol_ticker(symbol=symbol)["price"])
    except Exception:
        return 0.0


def _get_filters(symbol="BTCUSDT"):
    ex = _client.get_symbol_info(symbol)
    lot = next(f for f in ex["filters"] if f["filterType"] == "LOT_SIZE")
    return float(lot["minQty"]), float(lot["stepSize"])


def _round_step(qty: float, step: float) -> float:
    d = Decimal(str(qty))
    s = Decimal(str(step))
    return float((d // s) * s)


def sell_market_tool(percent: Optional[float] = None) -> Dict[str, Any]:
    """
    Executa uma venda parcial de BTCUSDT (modo dry ou real).

    Args:
        percent (float): percentual entre 1% e 40% do valor alavancado.
    """
    if percent is None:
        percent = 40.0

    if percent <= 0 or percent > 40:
        return {
            "ok": False,
            "error": "Percentual inválido. Somente entre 1% e 40% é permitido.",
        }

    price = _get_price("BTCUSDT")

    acc = _client.get_margin_account()
    total_alavancado = float(acc.get("totalAssetOfBtc", 0.0)) * price
    value_to_sell = (percent / 100.0) * total_alavancado

    # Checa valor mínimo (~10 USDT)
    if value_to_sell < 10:
        return {
            "ok": False,
            "error": f"Valor muito baixo ({value_to_sell:.2f} USDT). Mínimo de 10 USDT para executar a venda.",
        }

    qty_raw = value_to_sell / price
    min_qty, step = _get_filters("BTCUSDT")
    qty = max(_round_step(qty_raw, step), min_qty)

    # Modo dry-run (simulação)
    if TRADING_MODE == "dry":
        return {
            "ok": True,
            "mode": "DRY_RUN",
            "requested_percent": percent,
            "qty_btc": qty,
            "price": price,
            "value_usdt": round(qty * price, 2),
            "msg": f"Simulação de venda de {percent}% (~{qty:.6f} BTC).",
        }

    # Execução real
    try:
        order = _client.create_margin_order(
            symbol="BTCUSDT",
            side="SELL",
            type="MARKET",
            quantity=qty,
            sideEffectType="AUTO_REPAY",
        )
        return {
            "ok": True,
            "mode": "REAL",
            "requested_percent": percent,
            "qty_btc": qty,
            "price": price,
            "value_usdt": round(qty * price, 2),
            "exchange_ack": order,
            "msg": f"Venda parcial de {qty:.6f} BTC executada com sucesso ao preço de {price:.2f}.",
        }

    except BinanceAPIException as e:
        return {"ok": False, "error": f"Binance APIError: {e.message}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
