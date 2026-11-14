# ==============================================================
# 💰 Tool: sell_market_tool — venda parcial de BTCUSDT (1%–40%)
# ==============================================================

import os
import math
from decimal import Decimal
from typing import Dict, Any, Optional
from binance.client import Client
from binance.exceptions import BinanceAPIException
from ..config import get_trading_mode

BNB_API_KEY = os.getenv("BNB_API_KEY")
BNB_API_SECRET = os.getenv("BNB_API_SECRET")
TRADING_MODE = get_trading_mode()

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


def sell_market_tool(
    percent: Optional[float] = None,
    confirmed: bool = False,
) -> Dict[str, Any]:
    """
    Executa uma venda parcial de BTCUSDT (modo dry ou real).

    Args:
        percent (float): percentual entre 1% e 40% do valor alavancado.
    """
    if percent is None:
        return {"ok": False, "error": "Informe um percentual entre 1 e 40."}

    try:
        percent = float(percent)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Percentual deve ser um número entre 1 e 40."}

    if not math.isfinite(percent) or percent < 1 or percent > 40:
        return {
            "ok": False,
            "error": "Percentual inválido. Somente entre 1% e 40% é permitido.",
        }

    if TRADING_MODE == "real" and confirmed is not True:
        return {"ok": False, "error": "Confirmação explícita é obrigatória para venda real."}

    price = _get_price("BTCUSDT")
    if price <= 0:
        return {"ok": False, "error": "Preço BTCUSDT indisponível."}

    try:
        acc = _client.get_margin_account()
        btc_asset = next(asset for asset in acc.get("userAssets", []) if asset.get("asset") == "BTC")
        available_btc = float(btc_asset.get("free", 0.0))
    except Exception as exc:
        return {"ok": False, "error": f"Saldo BTC livre indisponível: {exc}"}

    requested_qty = available_btc * (percent / 100.0)
    value_to_sell = requested_qty * price

    # Checa valor mínimo (~10 USDT)
    if value_to_sell < 10:
        return {
            "ok": False,
            "error": f"Valor muito baixo ({value_to_sell:.2f} USDT). Mínimo de 10 USDT para executar a venda.",
        }

    qty_raw = value_to_sell / price
    min_qty, step = _get_filters("BTCUSDT")
    qty = _round_step(qty_raw, step)
    if qty < min_qty:
        return {"ok": False, "error": "Quantidade solicitada abaixo do mínimo negociável."}

    # Modo dry-run (simulação)
    if TRADING_MODE == "dry":
        return {
            "ok": True,
            "mode": "DRY_RUN",
            "requested_percent": percent,
            "percent_basis": "free_btc_balance",
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
        executed_qty = float(order.get("executedQty", 0)) if isinstance(order, dict) else 0
        quote_qty = float(order.get("cummulativeQuoteQty", 0)) if isinstance(order, dict) else 0
        order_status = order.get("status") if isinstance(order, dict) else None
        if order_status not in {"PARTIALLY_FILLED", "FILLED"} or executed_qty <= 0:
            return {"ok": False, "error": "A Binance não confirmou execução da venda.", "exchange_ack": order}

        fill_price = quote_qty / executed_qty if quote_qty > 0 else price
        return {
            "ok": True,
            "mode": "REAL",
            "requested_percent": percent,
            "percent_basis": "free_btc_balance",
            "qty_btc": executed_qty,
            "price": fill_price,
            "value_usdt": round(quote_qty if quote_qty > 0 else executed_qty * fill_price, 2),
            "exchange_ack": order,
            "msg": f"Venda parcial de {executed_qty:.6f} BTC executada com sucesso ao preço de {fill_price:.2f}.",
        }

    except BinanceAPIException as e:
        return {"ok": False, "error": f"Binance APIError: {e.message}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
