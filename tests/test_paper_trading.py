from concurrent.futures import ThreadPoolExecutor

import pytest

from app.paper_trading import open_paper_position, process_paper_cycle


SETTINGS = {
    "stop_loss_pct": 5.0,
    "risk_reward": 2.0,
    "take_profit_pct": None,
    "fee_pct": 0.1,
    "slippage_pct": 0.1,
}


def test_open_position_calculates_levels_from_average_fill():
    position = open_paper_position(2, 100, 10, timestamp="2026-01-01T00:00:00", **SETTINGS)

    assert position["entry_price"] == pytest.approx(100.1)
    assert position["stop_price"] == pytest.approx(95.095)
    assert position["take_profit_price"] == pytest.approx(110.11)
    assert position["risk_reward"] == pytest.approx(2)
    assert position["entry_fee"] == pytest.approx(0.2002)


def test_explicit_take_profit_overrides_risk_reward_target():
    position = open_paper_position(
        1,
        100,
        1,
        stop_loss_pct=4,
        risk_reward=2,
        take_profit_pct=3,
        fee_pct=0,
        slippage_pct=0,
        timestamp="2026-01-01T00:00:00",
    )

    assert position["take_profit_price"] == pytest.approx(103)
    assert position["risk_reward"] == pytest.approx(0.75)


def test_take_profit_records_positive_net_result_after_costs():
    state = {
        "paper_position": open_paper_position(
            2, 100, 10, timestamp="2026-01-01T00:00:00", **SETTINGS
        ),
        "paper_trades": [],
    }

    updated_state, trade = process_paper_cycle(
        state, market_price=121, cycle=15, timestamp="2026-01-01T00:10:00"
    )

    assert updated_state is state
    assert trade["reason"] == "TAKE_PROFIT"
    assert trade["net_pnl"] > 0
    assert trade["fees_total"] == pytest.approx(trade["entry_fee"] + trade["exit_fee"])
    assert trade["max_favorable_excursion_pct"] == pytest.approx(21)
    assert trade["max_adverse_excursion_pct"] == pytest.approx(0)
    assert updated_state["paper_position"] is None
    assert len(updated_state["paper_trades"]) == 1


def test_stop_loss_gap_uses_worse_observed_price_and_net_loss():
    state = {
        "paper_position": open_paper_position(
            2, 100, 10, timestamp="2026-01-01T00:00:00", **SETTINGS
        ),
        "paper_trades": [],
    }

    _, trade = process_paper_cycle(
        state, market_price=90, cycle=12, timestamp="2026-01-01T00:04:00"
    )

    assert trade["reason"] == "STOP_LOSS"
    assert trade["exit_price"] < trade["stop_price"]
    assert trade["net_pnl"] < 0
    assert trade["max_adverse_excursion_pct"] == pytest.approx(-10)
    assert trade["cycle_duration"] == 2


def test_repeated_exit_evaluation_cannot_close_or_sell_twice():
    state = {
        "paper_position": open_paper_position(
            1, 100, 1, timestamp="2026-01-01T00:00:00", **SETTINGS
        ),
        "paper_trades": [],
    }

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: process_paper_cycle(state, 90, 2), range(32)))

    close_events = [trade for _, trade in results if trade is not None]
    assert len(close_events) == 1
    assert len(state["paper_trades"]) == 1
    assert state["paper_position"] is None


def test_untriggered_volatile_price_keeps_position_open():
    state = {
        "paper_position": open_paper_position(
            1, 100, 1, timestamp="2026-01-01T00:00:00", **SETTINGS
        ),
        "paper_trades": [],
    }

    updated_state, trade = process_paper_cycle(state, 110, 2)

    assert trade is None
    assert updated_state["paper_position"]["status"] == "OPEN"
    assert updated_state["paper_trades"] == []


def test_invalid_risk_settings_are_rejected():
    with pytest.raises(ValueError, match="stop_loss_pct"):
        open_paper_position(1, 100, 1, stop_loss_pct=0, **{key: value for key, value in SETTINGS.items() if key != "stop_loss_pct"})
