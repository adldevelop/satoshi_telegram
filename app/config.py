import os

from dotenv import load_dotenv
from .paper_trading import _validate_settings


load_dotenv()


def get_trading_mode() -> str:
    mode = os.getenv("TRADING_MODE", "dry").strip().lower()
    if mode not in {"dry", "real"}:
        raise ValueError("TRADING_MODE must be either 'dry' or 'real'.")
    return mode


def get_buy_percent() -> float:
    try:
        percent = float(os.getenv("BUY_PERCENT", "0.4"))
    except ValueError as exc:
        raise ValueError("BUY_PERCENT must be a number between 0 and 1.") from exc

    if not 0 < percent <= 1:
        raise ValueError("BUY_PERCENT must be greater than 0 and at most 1.")
    return percent


def get_paper_settings() -> dict:
    try:
        stop_loss_pct = float(os.getenv("PAPER_STOP_LOSS_PCT", "1.0"))
        risk_reward = float(os.getenv("PAPER_RISK_REWARD", "2.0"))
        fee_pct = float(os.getenv("PAPER_FEE_PCT", "0.1"))
        slippage_pct = float(os.getenv("PAPER_SLIPPAGE_PCT", "0.05"))
        take_profit_value = os.getenv("PAPER_TAKE_PROFIT_PCT", "").strip()
        take_profit_pct = float(take_profit_value) if take_profit_value else None
    except ValueError as exc:
        raise ValueError("Paper-trading settings must be valid numbers.") from exc

    _validate_settings(stop_loss_pct, risk_reward, take_profit_pct, fee_pct, slippage_pct)
    return {
        "stop_loss_pct": stop_loss_pct,
        "risk_reward": risk_reward,
        "take_profit_pct": take_profit_pct,
        "fee_pct": fee_pct,
        "slippage_pct": slippage_pct,
    }