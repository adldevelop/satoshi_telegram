import math
import threading
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

_PAPER_STATE_LOCK = threading.Lock()


def _validate_settings(
    stop_loss_pct: float,
    risk_reward: float,
    take_profit_pct: Optional[float],
    fee_pct: float,
    slippage_pct: float,
) -> None:
    values = (stop_loss_pct, risk_reward, fee_pct, slippage_pct)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Paper-trading settings must be finite numbers.")
    if not 0 < stop_loss_pct < 100:
        raise ValueError("stop_loss_pct must be between 0 and 100.")
    if risk_reward <= 0:
        raise ValueError("risk_reward must be greater than 0.")
    if fee_pct < 0 or slippage_pct < 0 or fee_pct >= 100 or slippage_pct >= 100:
        raise ValueError("fee_pct and slippage_pct must be between 0 and 100.")
    if take_profit_pct is not None and (
        not math.isfinite(take_profit_pct) or take_profit_pct <= 0
    ):
        raise ValueError("take_profit_pct must be positive when configured.")


def open_paper_position(
    quantity: float,
    market_price: float,
    cycle: int,
    stop_loss_pct: float = 1.0,
    risk_reward: float = 2.0,
    take_profit_pct: Optional[float] = None,
    fee_pct: float = 0.1,
    slippage_pct: float = 0.05,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    _validate_settings(stop_loss_pct, risk_reward, take_profit_pct, fee_pct, slippage_pct)
    if not math.isfinite(quantity) or quantity <= 0:
        raise ValueError("quantity must be a positive finite number.")
    if not math.isfinite(market_price) or market_price <= 0:
        raise ValueError("market_price must be a positive finite number.")

    entry_price = market_price * (1 + slippage_pct / 100)
    target_pct = take_profit_pct if take_profit_pct is not None else stop_loss_pct * risk_reward
    return {
        "id": f"paper-{cycle}-{timestamp or datetime.now().isoformat()}",
        "status": "OPEN",
        "cycle": cycle,
        "opened_at": timestamp or datetime.now().isoformat(),
        "quantity": quantity,
        "entry_market_price": market_price,
        "entry_price": entry_price,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": target_pct,
        "risk_reward": target_pct / stop_loss_pct,
        "stop_price": entry_price * (1 - stop_loss_pct / 100),
        "take_profit_price": entry_price * (1 + target_pct / 100),
        "fee_pct": fee_pct,
        "slippage_pct": slippage_pct,
        "entry_fee": entry_price * quantity * fee_pct / 100,
        "observed_prices": [market_price],
    }


def evaluate_paper_exit(
    position: Optional[Dict[str, Any]],
    market_price: float,
    cycle: int,
    timestamp: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not position or position.get("status") != "OPEN":
        return None
    if not math.isfinite(market_price) or market_price <= 0:
        return None

    if market_price <= float(position["stop_price"]):
        reason = "STOP_LOSS"
    elif market_price >= float(position["take_profit_price"]):
        reason = "TAKE_PROFIT"
    else:
        return None

    quantity = float(position["quantity"])
    exit_price = market_price * (1 - float(position["slippage_pct"]) / 100)
    exit_fee = exit_price * quantity * float(position["fee_pct"]) / 100
    gross_pnl = (exit_price - float(position["entry_price"])) * quantity
    net_pnl = gross_pnl - float(position["entry_fee"]) - exit_fee
    observed_prices = [
        float(price)
        for price in position.get("observed_prices", [position["entry_market_price"]])
        if isinstance(price, (int, float)) and math.isfinite(float(price)) and price > 0
    ]
    observed_prices.append(market_price)
    entry_market_price = float(position["entry_market_price"])
    price_moves = [(price / entry_market_price - 1) * 100 for price in observed_prices]
    return {
        "id": position["id"],
        "status": "CLOSED",
        "reason": reason,
        "cycle": cycle,
        "opened_at": position["opened_at"],
        "closed_at": timestamp or datetime.now().isoformat(),
        "quantity": quantity,
        "entry_market_price": float(position["entry_market_price"]),
        "entry_price": float(position["entry_price"]),
        "exit_market_price": market_price,
        "exit_price": exit_price,
        "stop_price": float(position["stop_price"]),
        "take_profit_price": float(position["take_profit_price"]),
        "stop_loss_pct": float(position["stop_loss_pct"]),
        "take_profit_pct": float(position["take_profit_pct"]),
        "risk_reward": float(position["risk_reward"]),
        "gross_pnl": gross_pnl,
        "entry_fee": float(position["entry_fee"]),
        "exit_fee": exit_fee,
        "fees_total": float(position["entry_fee"]) + exit_fee,
        "net_pnl": net_pnl,
        "return_pct_on_entry_notional": net_pnl / (float(position["entry_price"]) * quantity) * 100,
        "max_favorable_excursion_pct": max(price_moves),
        "max_adverse_excursion_pct": min(price_moves),
        "cycle_duration": cycle - int(position["cycle"]),
    }


def process_paper_cycle(
    state: Dict[str, Any],
    market_price: float,
    cycle: int,
    stop_loss_pct: float = 1.0,
    risk_reward: float = 2.0,
    take_profit_pct: Optional[float] = None,
    fee_pct: float = 0.1,
    slippage_pct: float = 0.05,
    timestamp: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Advance shared paper state; concurrent evaluators can close only once."""
    with _PAPER_STATE_LOCK:
        position = state.get("paper_position")
        closed_trade = evaluate_paper_exit(position, market_price, cycle, timestamp)
        if closed_trade is None:
            if position and position.get("status") == "OPEN" and math.isfinite(market_price) and market_price > 0:
                prices = list(position.get("observed_prices", []))
                prices.append(market_price)
                position["observed_prices"] = prices[-50_000:]
            return state, None

        state["paper_position"] = None
        trades = list(state.get("paper_trades", []))
        trades.append(closed_trade)
        state["paper_trades"] = trades[-500:]
        state["last_paper_exit_id"] = closed_trade["id"]
        return state, closed_trade