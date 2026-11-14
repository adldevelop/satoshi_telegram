import json
from datetime import datetime, timedelta

import pytest

from app.daily_review import build_review, load_log_rows, render_report, run_daily_review_if_due


def _row(timestamp, mode="dry", status="NO_ENTRY", price=None, error=None):
    extra = {"error": error} if error else {}
    if status == "SIMULATED_BUY":
        extra.update({"price": price, "quantity": 0.01})
    return {
        "timestamp": timestamp.isoformat(),
        "mode": mode,
        "status": status,
        "analysis": "",
        "market_price": price,
        "extra": extra,
    }


def test_review_separates_modes_and_measures_hypothetical_followup():
    now = datetime(2026, 1, 10, 12)
    rows = [
        _row(now - timedelta(hours=48), status="SIMULATED_BUY", price=100.0),
        _row(now - timedelta(hours=36), price=110.0),
        _row(now - timedelta(hours=24), price=95.0),
        _row(now - timedelta(hours=2), status="ERROR", error="Binance API error"),
        _row(now - timedelta(hours=1), mode="real", status="ERROR", error="private detail"),
    ]
    for row in rows:
        row["_parsed_at"] = datetime.fromisoformat(row["timestamp"])

    review = build_review(rows, current_mode="dry", now=now)

    assert review["last_24h"]["dry_cycles"] == 2
    assert review["last_24h"]["dry_errors"] == 1
    assert review["last_24h"]["dry_error_categories"] == {"Binance API error": 1}
    assert review["last_7d"]["dry_entries"] == 1
    assert review["last_7d"]["dry_errors"] == 1
    assert review["historical_real_rows_7d"] == 1
    assert review["paper_followup_24h"]["completed_windows"] == 1
    assert review["paper_followup_24h"]["avg_mfe_pct"] == pytest.approx(10)
    assert review["paper_followup_24h"]["avg_mae_pct"] == pytest.approx(-5)
    assert "não representam lucro realizado" in render_report(review)
    assert "private detail" not in render_report(review)


def test_load_log_rows_reads_rotated_files_in_time_order(tmp_path):
    current = tmp_path / "satoshi_log.jsonl"
    backup = tmp_path / "satoshi_log.jsonl.1"
    backup.write_text(json.dumps(_row(datetime(2026, 1, 1))) + "\n", encoding="utf-8")
    current.write_text(json.dumps(_row(datetime(2026, 1, 2))) + "\n", encoding="utf-8")

    rows = load_log_rows(str(current))

    assert [row["timestamp"] for row in rows] == [
        "2026-01-01T00:00:00",
        "2026-01-02T00:00:00",
    ]


def test_daily_review_writes_once_per_date_and_notifies(tmp_path):
    log_path = tmp_path / "satoshi_log.jsonl"
    output_path = tmp_path / "daily_review.md"
    state_path = tmp_path / "daily_review_state.json"
    now = datetime(2026, 1, 10, 12)
    log_path.write_text(json.dumps(_row(now - timedelta(minutes=2))) + "\n", encoding="utf-8")
    messages = []

    first = run_daily_review_if_due(
        str(log_path),
        str(output_path),
        str(state_path),
        current_mode="dry",
        notifier=messages.append,
        now=now,
    )
    second = run_daily_review_if_due(
        str(log_path),
        str(output_path),
        str(state_path),
        current_mode="dry",
        notifier=messages.append,
        now=now + timedelta(hours=1),
    )

    assert first is not None
    assert second is None
    assert output_path.exists()
    assert json.loads(state_path.read_text(encoding="utf-8"))["last_review_date"] == "2026-01-10"
    assert len(messages) == 1
    assert "revisão diária dry-run" in messages[0]