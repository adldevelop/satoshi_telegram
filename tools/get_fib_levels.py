# app/tools/get_fib_levels.py
import os
from datetime import datetime
from typing import Dict, Any

from dotenv import load_dotenv
from binance.client import Client
from google.adk.tools.function_tool import FunctionTool

# ==========================================================
# ⚙️ Configuração Inicial
# ==========================================================
load_dotenv()

BNB_API_KEY = os.getenv("BNB_API_KEY")
BNB_SECRET_KEY = os.getenv("BNB_SECRET_KEY")

_client = Client(BNB_API_KEY, BNB_SECRET_KEY)


# ==========================================================
# 🔹 Função auxiliar — cálculo de retrações de Fibonacci
# ==========================================================
def _fib_levels(high_val: float, low_val: float) -> Dict[str, float]:
    rng = high_val - low_val
    return {
        "0.236": low_val + rng * 0.236,
        "0.382": low_val + rng * 0.382,
        "0.5":   low_val + rng * 0.5,
        "0.618": low_val + rng * 0.618,
        "0.786": low_val + rng * 0.786,
    }


# ==========================================================
# 🔹 Função principal do Tool
# ==========================================================
def get_fib_levels(symbol: str) -> Dict[str, Any]:
    """
    Retorna máximas e mínimas do BTCUSDT em 4 meses (4H), níveis de Fibonacci,
    e snapshot diário com preço atual, alta/baixa e volume das últimas 24h.
    """
    try:
        candles_4h = _client.get_klines(
            symbol=symbol,
            interval=Client.KLINE_INTERVAL_4HOUR,
            limit=720,  # 4 meses ≈ 120 dias * 6 candles/dia
        )

        if not candles_4h:
            return {"ok": False, "error": "Falha ao obter klines 4H (4 meses)."}

        highs = [float(c[2]) for c in candles_4h]
        lows = [float(c[3]) for c in candles_4h]
        high_4m = max(highs)
        low_4m = min(lows)
        fib = _fib_levels(high_4m, low_4m)

        ticker = _client.get_ticker(symbol=symbol)
        price = float(ticker.get("lastPrice", 0))
        try:
            stats_24h = _client.ticker_24hr(symbol=symbol)
        except AttributeError:
            stats_24h = _client.get_ticker(symbol=symbol)

        return {
            "ok": True,
            "symbol": symbol,
            "timeframe": "4H",
            "lookback_months": 4,
            "high_4m": high_4m,
            "low_4m": low_4m,
            "fib": fib,
            "snapshot": {
                "price": float(stats_24h.get("lastPrice", price)),
                "day_high": float(stats_24h.get("highPrice", 0)),
                "day_low": float(stats_24h.get("lowPrice", 0)),
                "day_volume": float(stats_24h.get("volume", 0)),
            },
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print("❌ ERRO em get_fib_levels():", tb)
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)}"}



# ==========================================================
# 🔹 Registro compatível do Tool no ADK (sem name/desc)
# ==========================================================
get_fib_levels_tool = FunctionTool(get_fib_levels)
