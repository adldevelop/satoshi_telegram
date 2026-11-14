# ============================================================
# create_order.py — versão aprimorada para o agente Satoshi 🤖
# ============================================================

import os
import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode
from decimal import Decimal, ROUND_DOWN, getcontext
from ..config import get_buy_percent, get_trading_mode



# ============================================================
# ⚙️ Inicialização e Configurações
# ============================================================

BNB_API_KEY = os.getenv("BNB_API_KEY")
BNB_API_SECRET = os.getenv("BNB_API_SECRET")
MARGIN_BASE_URL = "https://api.binance.com"

# Precisão retirada do exchangeInfo
exchange_precision = {
    "BTCUSDT": {"price_tick": Decimal("0.10"), "qty_step": Decimal("0.00001000")},
}

# ============================================================
# 🧩 Funções utilitárias
# ============================================================

def decimal_places(d: Decimal) -> int:
    """Conta o número de casas decimais válidas."""
    s = format(d, "f")
    return len(s.split(".")[1].rstrip("0")) if "." in s else 0


def sign_params(params: dict) -> str:
    """Assina a query string com HMAC-SHA256 para autenticação Binance."""
    params["timestamp"] = int(time.time() * 1000)
    query_string = urlencode(params)
    signature = hmac.new(
        BNB_API_SECRET.encode("utf8"),
        query_string.encode("utf8"),
        hashlib.sha256,
    ).hexdigest()
    params["signature"] = signature
    return urlencode(params)


def get_ticker_price(symbol: str) -> float | None:
    """Obtém o preço atual do ativo."""
    url = f"{MARGIN_BASE_URL}/api/v3/ticker/price"
    params = {"symbol": symbol}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return float(response.json()["price"])
    except Exception as e:
        print(f"[❌] Erro ao obter preço para {symbol}: {e}")
        return None


def get_margin_account_balance(asset: str = "USDT") -> float | None:
    """
    Obtém o saldo disponível (free) na conta de margem da Binance.
    Pode ser usado tanto em cross margin quanto em isolated margin.
    """
    endpoint = "/sapi/v1/margin/account"
    params = {}
    query_string = sign_params(params)
    url = f"{MARGIN_BASE_URL}{endpoint}?{query_string}"
    headers = {"X-MBX-APIKEY": BNB_API_KEY}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        for asset_info in data.get("userAssets", []):
            if asset_info.get("asset") == asset:
                free_balance = float(asset_info.get("free", 0))
                print(f"[💰] Saldo disponível em {asset}: {free_balance}")
                return free_balance
        print(f"[⚠️] Ativo {asset} não encontrado na conta de margem.")
        return 0.0
    except Exception as e:
        print(f"[❌] Erro ao obter saldo de {asset}: {e}")
        return None


def create_margin_order(symbol: str, side: str, quantity: float, order_type="MARKET"):
    """Executa uma ordem de margem (MARGIN_BUY) na Binance."""
    if get_trading_mode() != "real":
        return None
    if not BNB_API_KEY or not BNB_API_SECRET:
        return None
    endpoint = "/sapi/v1/margin/order"
    params = {
        "symbol": symbol,
        "side": side.upper(),
        "type": order_type,
        "quantity": str(quantity),
        "isIsolated": "FALSE",
        "sideEffectType": "MARGIN_BUY" if side.upper() == "BUY" else "NO_SIDE_EFFECT",
    }
    query_string = sign_params(params)
    url = f"{MARGIN_BASE_URL}{endpoint}?{query_string}"
    headers = {"X-MBX-APIKEY": BNB_API_KEY}

    try:
        response = requests.post(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"[✅] Ordem {side.upper()} executada com sucesso para {symbol}: {data}")
        return data
    except Exception as e:
        print(f"[❌] Erro ao executar ordem {side.upper()} para {symbol}: {e}")
        return None

# ============================================================
# 🧠 Tool principal — chamada pelo agente Satoshi
# ============================================================


def create_order_tool(
    symbol: str = "BTCUSDT",
    leverage: int = 5,
    percent_capital: float | None = None,
):
    """
    Cria uma ordem de compra (MARGIN_BUY) de BTC na Binance com base no saldo atual disponível.

    O agente calcula automaticamente:
    - O saldo livre de USDT na conta de margem.
    - O valor de entrada definido por BUY_PERCENT (ou percent_capital explícito).
    - A quantidade proporcional de BTC considerando alavancagem de 5x.

    Args:
        symbol (str): Par de negociação (ex: "BTCUSDT").
        leverage (int): Multiplicador de alavancagem (default = 5).
        percent_capital (float): Fração do saldo disponível a ser utilizada (0 < valor <= 1).

    Returns:
        dict: Dados estruturados da operação (preço, quantidade, capital usado, status).
    """

    try:
        trading_mode = get_trading_mode()
    except ValueError as exc:
        return {"status": "ERROR", "message": str(exc)}

    if not isinstance(leverage, int) or leverage <= 0:
        return {"status": "ERROR", "message": "leverage deve ser um inteiro positivo."}

    # 🔐 Validação de credenciais
    if not BNB_API_KEY or not BNB_API_SECRET:
        return {"status": "ERROR", "message": "Credenciais da Binance ausentes. Verifique o arquivo .env."}

    # 💰 Consulta de saldo
    balance_usdt = get_margin_account_balance("USDT")
    if balance_usdt is None or balance_usdt <= 0:
        return {"status": "ERROR", "message": "Não foi possível obter saldo de USDT ou saldo insuficiente."}

    # 💵 Cálculo do valor de entrada
    if percent_capital is None:
        percent_capital = get_buy_percent()
    if not 0 < percent_capital <= 1:
        return {"status": "ERROR", "message": "percent_capital deve estar entre 0 e 1."}

    capital_to_use = balance_usdt * percent_capital
    print(f"[📊] Capital total em USDT: {balance_usdt} | Usando {percent_capital*100:.0f}% = {capital_to_use:.2f} USDT")

    # 💹 Obter preço atual
    current_price = get_ticker_price(symbol)
    if current_price is None:
        return {"status": "ERROR", "message": f"Falha ao obter preço de {symbol}"}

    # 🧮 Cálculo da quantidade ajustada à precisão
    effective_investment = capital_to_use * leverage
    raw_quantity = effective_investment / current_price
    qty_step = exchange_precision[symbol]["qty_step"]
    precision_qty = decimal_places(qty_step)

    getcontext().prec = 10
    quantity_decimal = Decimal(str(raw_quantity)).quantize(
        Decimal("1e-" + str(precision_qty)), rounding=ROUND_DOWN
    )
    quantity = float(quantity_decimal)

    if quantity * current_price < 10:
        return {
            "status": "CANCELLED",
            "message": f"Valor abaixo do mínimo exigido pela Binance (10 USDT). Total: {quantity * current_price:.2f} USDT",
        }

    print(f"[⚙️] Executando ordem BUY para {symbol}")
    print(f"Preço atual: {current_price} | Quantidade: {quantity} | Alavancagem: {leverage}x")

    if trading_mode == "dry":
        return {
            "status": "SIMULATED",
            "symbol": symbol,
            "price": current_price,
            "quantity": quantity,
            "leverage": leverage,
            "capital_used_usdt": round(capital_to_use, 2),
            "mode": "DRY_RUN",
        }

    # 🚀 Execução da ordem
    order_response = create_margin_order(symbol, "BUY", quantity)
    executed_qty = float(order_response.get("executedQty", 0)) if isinstance(order_response, dict) else 0
    order_status = order_response.get("status") if isinstance(order_response, dict) else None
    if order_status in {"PARTIALLY_FILLED", "FILLED"} and executed_qty > 0:
        return {
            "status": "ORDER_EXECUTED",
            "symbol": symbol,
            "price": current_price,
            "quantity": executed_qty,
            "leverage": leverage,
            "capital_used_usdt": round(capital_to_use, 2),
            "timestamp": int(time.time()),
            "response": order_response,
        }

    return {"status": "ERROR", "message": "Falha ao executar ordem na Binance"}
