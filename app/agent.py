# ==============================================================
# 🧠 Satoshi Agent — Margin Trader BTC (ADK 1.16.0 + MARGIN + Leverage 5x)
# ==============================================================

import asyncio
import os
import time
import json
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from .config import get_buy_percent, get_trading_mode
from .tools.get_market_data import get_market_data
from binance.client import Client
import requests

# ==============================================================
# ⚙️ Configurações iniciais
# ==============================================================

BNB_API_KEY = os.getenv("BNB_API_KEY")
BNB_API_SECRET = os.getenv("BNB_API_SECRET")
TRADING_MODE = get_trading_mode()
COOLDOWN_CYCLES = int(os.getenv("COOLDOWN_CYCLES", "180")) #180
USE_REASONING = os.getenv("USE_REASONING", "off").lower().strip() == "on"
GENAI_API_KEY = os.getenv("GEMINI_API_KEY")

# 🔔 Config Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

client = Client(BNB_API_KEY, BNB_API_SECRET)

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "satoshi_log.jsonl")
STATE_FILE = os.path.join(LOG_DIR, "state.json")
PNL_HISTORY_FILE = os.path.join(LOG_DIR, "pnl_history.json")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "3"))

#===============================================================
#                     BUY PERCENT CONFIG
#===============================================================
BUY_PERCENT = get_buy_percent()
LEVERAGE = int(os.getenv("LEVERAGE", "5"))

# 🔔 Percentual mínimo de movimento para enviar alerta (ex: 0.5 = 0.5%)
PRICE_MOVE_ALERT_PCT = float(os.getenv("PRICE_MOVE_ALERT_PCT", "0.5"))

# ==============================================================
# 🔔 Função utilitária para Telegram
# ==============================================================

def send_telegram_message(text: str) -> None:
    """Envia uma mensagem simples para o Telegram do usuário."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        # Não quebra o bot se não tiver configurado
        print("ℹ️ Telegram não configurado (TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID ausentes).")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}

    try:
        resp = requests.post(url, data=payload, timeout=5)
        resp.raise_for_status()
    except Exception as e:
        print(f"[⚠️] Erro ao enviar mensagem Telegram: {e}")

# ==============================================================
# ==============================================================
# 🗃️ Estado persistente (cooldown + histórico)
# ==============================================================

def _ensure_dirs() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)

def load_state() -> Dict[str, Any]:
    _ensure_dirs()
    if not os.path.exists(STATE_FILE):
        return {"last_entry_cycle": None, "entries": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("last_entry_cycle", None)
            data.setdefault("entries", [])
            return data
    except Exception:
        return {"last_entry_cycle": None, "entries": []}

def save_state(state: Dict[str, Any]) -> None:
    _ensure_dirs()
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def _rotate_log_file(path: str, max_bytes: int, backup_count: int) -> None:
    if max_bytes <= 0 or not os.path.exists(path) or os.path.getsize(path) < max_bytes:
        return

    if backup_count <= 0:
        os.remove(path)
        return

    oldest_backup = f"{path}.{backup_count}"
    if os.path.exists(oldest_backup):
        os.remove(oldest_backup)

    for backup_index in range(backup_count - 1, 0, -1):
        source = f"{path}.{backup_index}"
        if os.path.exists(source):
            os.replace(source, f"{path}.{backup_index + 1}")

    os.replace(path, f"{path}.1")

# ==============================================================
# 📁 Logger estruturado
# ==============================================================

def salvar_log(ciclo, fibo_data, balances, analise, status, extra=None, entries=None, cooldown_meta=None, perf_data=None, preco_medio=None):
    _ensure_dirs()
    registro = {
        "timestamp": datetime.now().isoformat(),
        "cycle": ciclo,
        "mode": TRADING_MODE,
        "fibo_data": fibo_data,
        "balances": balances,
        "analysis": analise,
        "status": status,
        "cooldown": cooldown_meta,
        "extra": extra,
        "performance_30d": perf_data,
        "preco_medio_compra": preco_medio,
    }
    if entries is not None:
        registro["entries_count"] = len(entries)
        registro["entries_prices"] = [e.get("price") for e in entries if "price" in e]
    _rotate_log_file(LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")

# ==============================================================
# 💰 Saldos MARGIN Cross (BTC e USDT)
# ==============================================================

def get_balances_margin(account_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Lê saldos MARGIN Cross (BTC e USDT)."""
    try:
        account = account_data if account_data is not None else client.get_margin_account()
        assets = {a["asset"]: a for a in account["userAssets"]}
        btc, usdt = assets.get("BTC"), assets.get("USDT")

        def _f(x):
            try:
                return float(x)
            except:
                return None

        return {
            "BTC_free": _f(btc["free"]) if btc else 0,
            "BTC_borrowed": _f(btc["borrowed"]) if btc else 0,
            "BTC_interest": _f(btc["interest"]) if btc else 0,
            "USDT_free": _f(usdt["free"]) if usdt else 0,
            "USDT_borrowed": _f(usdt["borrowed"]) if usdt else 0,
            "USDT_interest": _f(usdt["interest"]) if usdt else 0,
        }
    except Exception as e:
        print(f"[⚠️] Erro ao obter saldo MARGIN: {e}")
        return None
    

# ==============================================================
# 📈 Cálculo de risco de liquidação
# ==============================================================

def calcular_risco_liquidacao(account_data: dict) -> Dict[str, Any]:
    """
    Calcula um score simples de risco de liquidação baseado em liability / net asset.
    É só um indicador qualitativo (Baixo, Médio, Alto).
    """
    try:
        total_net_btc = float(account_data.get("totalNetAssetOfBtc", 0) or 0)
        total_liab_btc = float(account_data.get("totalLiabilityOfBtc", 0) or 0)
        if total_net_btc <= 0:
            return {"ratio": None, "nivel": "DESCONHECIDO"}

        ratio = total_liab_btc / total_net_btc  # quanto da sua conta está “tomada” em dívida

        if ratio < 0.2:
            nivel = "BAIXO"
        elif ratio < 0.5:
            nivel = "MÉDIO"
        else:
            nivel = "ALTO"

        return {
            "ratio": round(ratio, 3),
            "nivel": nivel,
            "total_net_btc": total_net_btc,
            "total_liab_btc": total_liab_btc,
        }
    except Exception as e:
        return {"ratio": None, "nivel": f"ERRO: {e}"}

# ==============================================================
# 📈 Cálculo de performance e PnL (30 dias) + ROI (%)
# ==============================================================

def get_btc_price() -> float:
    try:
        ticker = client.get_symbol_ticker(symbol="BTCUSDT")
        return float(ticker["price"])
    except:
        return 0.0
    

def get_btc_prices_usd_brl() -> Dict[str, float]:
    """Retorna preço do BTC em USDT e BRL."""
    try:
        usd = float(client.get_symbol_ticker(symbol="BTCUSDT")["price"])
    except Exception:
        usd = 0.0
    try:
        brl = float(client.get_symbol_ticker(symbol="BTCBRL")["price"])
    except Exception:
        brl = 0.0
    return {"usd": usd, "brl": brl}


def get_margin_performance_30d(
    account_data: dict,
    btc_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Calcula performance dos últimos 30 dias (PnL, variação percentual e ROI)."""
    try:
        if btc_price is None:
            btc_price = get_btc_price()
        collateral_value = float(account_data.get("totalNetAssetOfBtc", 0)) * btc_price
        now = datetime.utcnow()
        past_threshold = now - timedelta(days=30)
        history = []

        if os.path.exists(PNL_HISTORY_FILE):
            with open(PNL_HISTORY_FILE, "r", encoding="utf-8") as f:
                try:
                    history = json.load(f)
                    history = [h for h in history if datetime.fromisoformat(h["timestamp"]) >= past_threshold]
                except:
                    history = []

        avg_collateral_30d = (
            sum(h["collateral_usdt"] for h in history) / len(history)
            if history else collateral_value
        )
        first_collateral = history[0]["collateral_usdt"] if history else collateral_value

        variation_pct = ((collateral_value - avg_collateral_30d) / avg_collateral_30d) * 100 if avg_collateral_30d > 0 else 0
        pnl_diff = collateral_value - avg_collateral_30d
        roi_pct = ((collateral_value - first_collateral) / first_collateral) * 100 if first_collateral > 0 else 0

        history.append({
            "timestamp": now.isoformat(),
            "collateral_usdt": collateral_value
        })
        with open(PNL_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

        return {
            "collateral_usdt": round(collateral_value, 2),
            "variation_pct_30d": round(variation_pct, 2),
            "pnl_diff_30d": round(pnl_diff, 2),
            "roi_pct": round(roi_pct, 2)
        }
    except Exception as e:
        return {"error": str(e)}

# ==============================================================
# 💹 Cálculo do preço médio de compra BTCUSDT
# ==============================================================

def calcular_preco_medio(entries: List[Dict[str, Any]]) -> Optional[float]:
    if not entries:
        return None
    soma = sum(e["price"] for e in entries)
    return round(soma / len(entries), 2)


def calcular_quantidade_compra(
    saldo_usdt: float,
    preco: float,
    percentual: float,
    alavancagem: int,
) -> float:
    if preco <= 0 or saldo_usdt <= 0:
        return 0.0
    quantidade = (saldo_usdt * percentual * alavancagem) / preco
    return float(Decimal(str(quantidade)).quantize(Decimal("0.00001"), rounding=ROUND_DOWN))

# ==============================================================
# 📊 Fibonacci (4H, 180 candles)
# ==============================================================

def get_fibonacci_levels(symbol="BTCUSDT"):
    candles = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_4HOUR, limit=180)
    highs = [float(c[2]) for c in candles]
    lows = [float(c[3]) for c in candles]
    hi, lo = max(highs), min(lows)
    retracoes = {
        "0.236": lo + (hi - lo) * 0.236,
        "0.382": lo + (hi - lo) * 0.382,
        "0.5": lo + (hi - lo) * 0.5,
        "0.618": lo + (hi - lo) * 0.618,
    }
    return {"high": hi, "low": lo, "retracoes": retracoes}


# ==============================================================
#  Monta Relatorio
# ==============================================================

def montar_relatorio_unico(
    preco_atual_usd: float,
    preco_atual_brl: float,
    fibo_data: dict,
    preco_medio: Optional[float],
    perf_data: dict,
    balances: Optional[dict],
    total_alavancado: Optional[float],
    diff_pct: Optional[float],
    price_move_limit: float,
    risco_liq: dict,
) -> str:
    retr_382 = float(fibo_data["retracoes"]["0.382"])
    retr_618 = float(fibo_data["retracoes"]["0.618"])
    zona_382_min, zona_382_max = retr_382 * 0.99, retr_382
    zona_618_min, zona_618_max = retr_618 * 0.99, retr_618

    preco_medio_txt = f"{preco_medio:.2f} USDT" if preco_medio else "—"

    movimento_txt = "—"
    if diff_pct is not None:
        movimento_txt = f"{diff_pct:.4f}% (limite alerta: {price_move_limit}%)"

    # saldo margin
    if balances:
        saldo_txt = (
            f"BTC_free: {balances['BTC_free']:.6f} | BTC_borrowed: {balances['BTC_borrowed']:.6f}\n"
            f"USDT_free: {balances['USDT_free']:.2f} | USDT_borrowed: {balances['USDT_borrowed']:.2f}"
        )
    else:
        saldo_txt = "Saldos MARGIN indisponíveis."

    # risco de liquidação
    if risco_liq.get("ratio") is not None:
        risco_txt = (
            f"Nível: {risco_liq['nivel']} | "
            f"Liability/Net: {risco_liq['ratio']} | "
            f"Net BTC: {risco_liq['total_net_btc']:.6f} | "
            f"Liab BTC: {risco_liq['total_liab_btc']:.6f}"
        )
    else:
        risco_txt = f"Nível: {risco_liq.get('nivel', 'DESCONHECIDO')}"

    total_alavancado_txt = f"{total_alavancado:.2f} USDT" if total_alavancado is not None else "—"

    relatorio = (
        "📊 Relatório do Satoshi Agent\n"
        f"Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "💰 Preços BTC:\n"
        f"• BTC/USDT: {preco_atual_usd:.2f} USDT\n"
        f"• BTC/BRL:  {preco_atual_brl:.2f} BRL\n\n"
        "📐 Fibonacci (4H / 180 candles):\n"
        f"• Topo: {fibo_data['high']:.2f}\n"
        f"• Fundo: {fibo_data['low']:.2f}\n"
        f"• 0.382: {retr_382:.2f} (zona: {zona_382_min:.2f} – {zona_382_max:.2f})\n"
        f"• 0.618: {retr_618:.2f} (zona: {zona_618_min:.2f} – {zona_618_max:.2f})\n\n"
        "📈 Performance (30d):\n"
        f"• Collateral: {perf_data.get('collateral_usdt', 0):.2f} USDT\n"
        f"• Variação 30d: {perf_data.get('variation_pct_30d', 0):.2f}% "
        f"({perf_data.get('pnl_diff_30d', 0):.2f} USDT)\n"
        f"• ROI: {perf_data.get('roi_pct', 0):.2f}%\n\n"
        "📉 Exposição e Risco:\n"
        f"• Total alavancado (aprox): {total_alavancado_txt}\n"
        f"• Risco de liquidação: {risco_txt}\n"
        f"• Movimento recente do preço: {movimento_txt}\n\n"
        "🎯 Estratégia atual:\n"
        f"• Preço médio de entrada BTCUSDT: {preco_medio_txt}\n"
        f"• Zona 0.382 alvo: {zona_382_min:.2f} – {zona_382_max:.2f}\n"
        f"• Zona 0.618 relevante: {zona_618_min:.2f} – {zona_618_max:.2f}\n\n"
        "💼 Saldos MARGIN Cross:\n"
        f"{saldo_txt}\n"
    )

    return relatorio


# ==============================================================
# ♻️ Loop Cognitivo de Mercado (MARGIN)
# ==============================================================

ultima_zona_fibo = None
zona_executada = False
ultimo_preco = None  # para alertas de movimento



async def monitorar_mercado(intervalo_segundos=120):
    global ultima_zona_fibo, zona_executada, ultimo_preco
    print(f"\n🚀 Satoshi Agent (MARGIN {LEVERAGE}x) iniciado — Modo: {'💻 Dry-Run' if TRADING_MODE=='dry' else '🔥 Execução Real'}\n")

    # 🔔 Notificação de inicialização do agente
    send_telegram_message(
        f"🚀 Satoshi Agent iniciado\n"
        f"Modo: {'DRY-RUN' if TRADING_MODE == 'dry' else 'REAL'}\n"
        f"Leverage: {LEVERAGE}x\n"
        f"Horário: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    state = load_state()
    last_entry_cycle = state.get("last_entry_cycle")
    entries = state.get("entries", [])
    ultimo_preco = state.get("last_price")  # recupera último preço salvo, se existir

    ciclo = entries[-1]["cycle"] + 1 if entries else 1
    start_time = time.time()

    while True:
        inicio = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"⏱️ Ciclo {ciclo} iniciado em {inicio}")

        try:
            market = get_market_data("BTCUSDT")
            preco_atual = float(market.get("price"))
            fibo_data = get_fibonacci_levels("BTCUSDT")
            fibo_382 = float(fibo_data["retracoes"]["0.382"])
            zona_min, zona_max = fibo_382 * 0.99, fibo_382

            zona_id = f"{fibo_data['high']:.2f}-{fibo_data['low']:.2f}-{fibo_382:.2f}"
            if ultima_zona_fibo != zona_id:
                print("🔄 Nova zona Fibonacci detectada — resetando execução.")
                ultima_zona_fibo, zona_executada = zona_id, False

            print(f"[📈] BTCUSDT → Preço: {preco_atual:.2f}")
            print(f"[🔢] Nível 0.382: {fibo_382:.2f} (zona: {zona_min:.2f} — {zona_max:.2f})")
            print(f"[📊] Estado: {'✅ Já executada' if zona_executada else '🟢 Aguardando entrada'}")

            account_data = client.get_margin_account()
            balances = get_balances_margin(account_data)
            perf_data = get_margin_performance_30d(account_data, preco_atual)
            preco_medio = calcular_preco_medio(entries)

            print(
                f"[📈] Collateral (30d): ${perf_data['collateral_usdt']} "
                f"({perf_data['variation_pct_30d']}%, {perf_data['pnl_diff_30d']} USDT)"
            )
            print(f"[📊] ROI consolidado: {perf_data['roi_pct']}%")

            # 💠 Total alavancado
            try:
                total_alavancado = float(account_data.get("totalAssetOfBtc", 0)) * preco_atual
                print(f"[💠] Total alavancado: ${total_alavancado:.2f}")
            except Exception as e:
                total_alavancado = None
                print(f"[⚠️] Erro ao obter total alavancado: {e}")

            if preco_medio:
                print(f"[💵] Preço médio de compra BTCUSDT: ${preco_medio}")

            if balances:
                print(
                    f"[💰] MARGIN → BTC_free: {balances['BTC_free']} (borrowed: {balances['BTC_borrowed']}), "
                    f"USDT_free: {balances['USDT_free']} (borrowed: {balances['USDT_borrowed']})"
                )
            else:
                print("[💰] MARGIN → não disponível.")

            # ============================================================
            # ⚡ ALERTA DE MOVIMENTO FORTE + RELATÓRIO COMPLETO
            # ============================================================
            diff_pct_val = None  # valor padrão

            if ultimo_preco is not None and ultimo_preco > 0:
                diff_pct = abs((preco_atual - ultimo_preco) / ultimo_preco) * 100
                diff_pct_val = diff_pct

                # 🔎 Log de debug para ver a variação
                print(f"[⚡] Movimento: {diff_pct:.4f}% (limite: {PRICE_MOVE_ALERT_PCT}%)")

                if diff_pct >= PRICE_MOVE_ALERT_PCT:
                    direction = "🔺" if preco_atual > ultimo_preco else "🔻"

                    # pega preços em USDT/BRL e risco de liquidação
                    prices = get_btc_prices_usd_brl()
                    risco_liq = calcular_risco_liquidacao(account_data)

                    relatorio = montar_relatorio_unico(
                        preco_atual_usd=preco_atual,
                        preco_atual_brl=prices["brl"],
                        fibo_data=fibo_data,
                        preco_medio=preco_medio,
                        perf_data=perf_data,
                        balances=balances,
                        total_alavancado=total_alavancado,
                        diff_pct=diff_pct,
                        price_move_limit=PRICE_MOVE_ALERT_PCT,
                        risco_liq=risco_liq,
                    )

                    # manda o alerta + o relatório completo
                    send_telegram_message(
                        f"⚡ Movimento forte no BTC ({diff_pct:.2f}%) {direction}\n\n" + relatorio
                    )

            # atualiza último preço para o próximo ciclo
            ultimo_preco = preco_atual

            # ============================================================
            # Cooldown e lógica de entrada
            # ============================================================
            cooldown_active = False
            if last_entry_cycle is not None and ciclo < last_entry_cycle + COOLDOWN_CYCLES:
                cooldown_active = True
                restante = (last_entry_cycle + COOLDOWN_CYCLES) - ciclo
                print(f"🚫 Cooldown ativo: {restante} ciclos restantes.")
            else:
                print("✅ Cooldown inativo.")

            analise_texto = (
                f"Análise determinística: preço {preco_atual:.2f}, zona [{zona_min:.2f} — {zona_max:.2f}]."
            )

            ciclo_status = "NO_ENTRY"

            if not cooldown_active and (zona_min <= preco_atual <= zona_max) and not zona_executada:
                print("🚨 Zona 0.382 atingida — executando ordem MARGIN (5x)...")
                free_usdt = balances["USDT_free"] if balances else 0
                qty = calcular_quantidade_compra(
                    free_usdt or 0,
                    preco_atual,
                    BUY_PERCENT,
                    LEVERAGE,
                )

                if qty <= 0 or qty * preco_atual < 10:
                    ciclo_status = "ORDER_REJECTED"
                    extra_payload = {
                        "reason": "Calculated order quantity is below the exchange minimum.",
                        "quantity": qty,
                        "notional_usdt": qty * preco_atual,
                    }
                elif TRADING_MODE == "dry":
                    payload = {
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "quantity": qty,
                        "price": preco_atual,
                        "leverage": LEVERAGE,
                        "timestamp": datetime.now().isoformat(),
                        "mode": "DRY_RUN",
                    }
                    print("🧪 [DRY-RUN] Ordem simulada:")
                    print(json.dumps(payload, indent=2))
                    ciclo_status = "SIMULATED_BUY"
                    extra_payload = payload

                    # 🔔 Notificação DRY-RUN
                    send_telegram_message(
                        f"🧪 [DRY-RUN] Entrada simulada BTCUSDT\n"
                        f"Preço: {preco_atual:.2f} USDT\n"
                        f"Qtd: {qty}\n"
                        f"Ciclo: {ciclo}\n"
                        f"Zona: 0.382 ({zona_min:.2f}–{zona_max:.2f})"
                    )
                    entries.append({
                        "cycle": ciclo,
                        "price": preco_atual,
                        "timestamp": datetime.now().isoformat(),
                        "mode": "DRY_RUN",
                    })
                    zona_executada = True
                    last_entry_cycle = ciclo
                else:
                    response = client.create_margin_order(
                        symbol="BTCUSDT",
                        side="BUY",
                        type="MARKET",
                        quantity=qty,
                        sideEffectType="MARGIN_BUY",
                    )
                    executed_qty = float(response.get("executedQty", 0)) if isinstance(response, dict) else 0
                    quote_qty = float(response.get("cummulativeQuoteQty", 0)) if isinstance(response, dict) else 0
                    order_status = response.get("status") if isinstance(response, dict) else None
                    ciclo_status = "ORDER_EXECUTED" if order_status in {"PARTIALLY_FILLED", "FILLED"} and executed_qty > 0 else "ORDER_FAILED"
                    extra_payload = {
                        "response": response,
                        "requested_qty": qty,
                        "executed_qty": executed_qty,
                    }

                    if ciclo_status == "ORDER_EXECUTED":
                        fill_price = quote_qty / executed_qty if quote_qty > 0 else preco_atual
                        entries.append({
                            "cycle": ciclo,
                            "price": fill_price,
                            "quantity": executed_qty,
                            "timestamp": datetime.now().isoformat(),
                        })
                        zona_executada = True
                        last_entry_cycle = ciclo
                        send_telegram_message(
                            f"✅ COMPRA EXECUTADA BTCUSDT\n"
                            f"Preço médio: {fill_price:.2f} USDT\n"
                            f"Qtd executada: {executed_qty}\n"
                            f"Leverage: {LEVERAGE}x\n"
                            f"Ciclo: {ciclo}\n"
                            f"Modo: REAL"
                        )

            # log e persistência de estado (com last_price)
            salvar_log(
                ciclo, fibo_data, balances, analise_texto, ciclo_status,
                extra_payload if ciclo_status != "NO_ENTRY" else None,
                entries, None,
                perf_data={**perf_data, "total_alavancado": total_alavancado},
                preco_medio=preco_medio
            )

            # 👉 salva estado com last_price também
            save_state({
                "last_entry_cycle": last_entry_cycle,
                "entries": entries,
                "last_price": ultimo_preco,
            })

            if entries:
                print("\n📒 Histórico de Entradas:")
                for e in entries[-5:]:
                    print(f"→ {e['price']} (ciclo {e['cycle']})")
            else:
                print("\n📒 Histórico vazio.")

        except Exception as e:
            print(f"⚠️ Erro no ciclo: {e}")
            salvar_log(ciclo, None, None, "ERROR", "ERROR", {"error": str(e)}, entries)

            # 🔔 Notificação de erro
            send_telegram_message(
                f"⚠️ ERRO no Satoshi Agent (ciclo {ciclo})\n"
                f"Detalhe: {e}"
            )

        tempo = (time.time() - start_time) / 60
        print(f"\n🕒 Aguardando {intervalo_segundos/60:.0f} minutos... | Tempo total: {tempo:.1f} min\n")
        ciclo += 1
        await asyncio.sleep(intervalo_segundos)

# ==============================================================
# 🧩 Ponto de entrada
# ==============================================================

if __name__ == "__main__":
    try:
        asyncio.run(monitorar_mercado())
    except KeyboardInterrupt:
        print("\n🛑 Satoshi finalizado manualmente.")
