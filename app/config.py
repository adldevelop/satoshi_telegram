import os

from dotenv import load_dotenv


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