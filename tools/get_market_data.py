# ============================================================
# 📈 Tool: get_market_data
# Retorna preço atual, máxima e mínima do dia de um par de moedas (ex: BTCUSDT)
# ============================================================

from binance.client import Client
import os

# Requer chave pública e privada no .env
BNB_API_KEY = os.getenv("BNB_API_KEY")
BNB_API_SECRET = os.getenv("BNB_API_SECRET")

def get_market_data(symbol: str) -> dict:
    try:
        client = Client(BNB_API_KEY, BNB_API_SECRET)
        ticker = client.get_ticker(symbol=symbol)
        return {
            "symbol": symbol,
            "price": float(ticker["lastPrice"]),
            "high": float(ticker["highPrice"]),
            "low": float(ticker["lowPrice"]),
            "volume": float(ticker["volume"]),
            "timestamp": ticker["closeTime"]
        }
    except Exception as e:
        return {"error": str(e)}
