import json
import os
import re
from collections import Counter, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


MAX_LOG_ROWS = 20_000
_PRICE_PATTERN = re.compile(r"preço\s+([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone().replace(tzinfo=None)
    return timestamp


def _log_files(log_path: Path) -> List[Path]:
    backups = []
    for candidate in log_path.parent.glob(f"{log_path.name}.*"):
        suffix = candidate.name.rsplit(".", 1)[-1]
        if candidate.is_file() and suffix.isdigit():
            backups.append((int(suffix), candidate))
    files = [path for _, path in sorted(backups, reverse=True)]
    if log_path.is_file():
        files.append(log_path)
    return files


def load_log_rows(log_path: str, max_rows: int = MAX_LOG_ROWS) -> List[Dict[str, Any]]:
    rows = deque(maxlen=max_rows)
    for path in _log_files(Path(log_path)):
        try:
            source = path.open(encoding="utf-8")
        except OSError:
            continue
        with source:
            for line in source:
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(row, dict):
                    continue
                timestamp = _parse_timestamp(row.get("timestamp"))
                if timestamp is None:
                    continue
                row["_parsed_at"] = timestamp
                rows.append(row)
    return sorted(rows, key=lambda row: row["_parsed_at"])


def _market_price(row: Dict[str, Any]) -> Optional[float]:
    value = row.get("market_price")
    if value is None:
        analysis = row.get("analysis")
        match = _PRICE_PATTERN.search(analysis) if isinstance(analysis, str) else None
        value = match.group(1) if match else None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def _error_category(row: Dict[str, Any]) -> str:
    extra = row.get("extra")
    message = str(extra.get("error", "")) if isinstance(extra, dict) else ""
    lowered = message.lower()
    if "apierror" in lowered or "binance api" in lowered:
        return "Binance API error"
    if "timeout" in lowered:
        return "Network timeout"
    if "connection" in lowered:
        return "Network connection error"
    match = re.match(r"([A-Za-z_][A-Za-z0-9_.]*)", message)
    return match.group(1) if match else "Unclassified error"


def _window_summary(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    selected = list(rows)
    modes = Counter(str(row.get("mode", "unknown")) for row in selected)
    statuses = Counter(str(row.get("status", "unknown")) for row in selected)
    dry_rows = [row for row in selected if row.get("mode") == "dry"]
    dry_errors = [row for row in dry_rows if row.get("status") == "ERROR"]
    categories = Counter(_error_category(row) for row in dry_errors)
    return {
        "rows": len(selected),
        "modes": dict(modes),
        "statuses": dict(statuses),
        "dry_cycles": len(dry_rows),
        "dry_errors": len(dry_errors),
        "dry_error_categories": dict(categories),
        "dry_entries": sum(row.get("status") == "SIMULATED_BUY" for row in dry_rows),
    }


def _paper_followup(
    rows: List[Dict[str, Any]],
    start: datetime,
    horizon_hours: int,
) -> Dict[str, Any]:
    dry_rows = [row for row in rows if row.get("mode") == "dry"]
    signals = [
        row for row in dry_rows
        if row.get("status") == "SIMULATED_BUY" and row["_parsed_at"] >= start
    ]
    horizon = timedelta(hours=horizon_hours)
    samples = []

    for signal in signals:
        extra = signal.get("extra")
        entry_price = extra.get("price") if isinstance(extra, dict) else None
        try:
            entry_price = float(entry_price)
        except (TypeError, ValueError):
            entry_price = _market_price(signal)
        if entry_price is None or entry_price <= 0:
            continue

        entry_time = signal["_parsed_at"]
        end_time = entry_time + horizon
        points = [entry_price]
        covered_until = entry_time
        for row in dry_rows:
            row_time = row["_parsed_at"]
            if entry_time < row_time <= end_time:
                price = _market_price(row)
                if price is not None:
                    points.append(price)
                    covered_until = max(covered_until, row_time)

        if covered_until < end_time:
            continue
        changes = [(price / entry_price - 1) * 100 for price in points]
        samples.append({"mfe_pct": max(changes), "mae_pct": min(changes)})

    return {
        "signals": len(signals),
        "completed_windows": len(samples),
        "avg_mfe_pct": sum(item["mfe_pct"] for item in samples) / len(samples) if samples else None,
        "avg_mae_pct": sum(item["mae_pct"] for item in samples) / len(samples) if samples else None,
    }


def build_review(
    rows: List[Dict[str, Any]],
    current_mode: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or datetime.now()
    if now.tzinfo is not None:
        now = now.astimezone().replace(tzinfo=None)
    last_24h = [row for row in rows if row["_parsed_at"] >= now - timedelta(hours=24)]
    last_7d = [row for row in rows if row["_parsed_at"] >= now - timedelta(days=7)]
    seven_day_start = now - timedelta(days=7)
    dry_price_rows = [
        row for row in last_7d
        if row.get("mode") == "dry" and _market_price(row) is not None
    ]
    paper_24h = _paper_followup(rows, seven_day_start, 24)

    recommendations = []
    dry_7d = _window_summary(last_7d)
    dry_24h = _window_summary(last_24h)
    if dry_7d["dry_cycles"] < 10:
        recommendations.append("Amostra de dry-run insuficiente para avaliar ou ajustar a estratégia.")
    if dry_7d["dry_entries"] == 0:
        recommendations.append("Nenhuma entrada simulada nos últimos 7 dias; ainda não há resultado de trade para avaliar.")
    elif paper_24h["completed_windows"] == 0:
        recommendations.append("Há sinais simulados, mas nenhum possui 24h de acompanhamento completo.")
    else:
        recommendations.append("MFE/MAE são apenas variações hipotéticas sem taxas, slippage, juros ou regra de saída.")
    if dry_24h["dry_errors"]:
        recommendations.append("Priorizar a investigação das falhas de API do dry-run antes de alterar parâmetros de entrada.")
    if not dry_price_rows:
        recommendations.append("Sem preços estruturados recentes; manter o relatório como diagnóstico operacional, não de performance.")

    return {
        "generated_at": now.isoformat(),
        "current_mode": current_mode,
        "last_24h": dry_24h,
        "last_7d": dry_7d,
        "paper_followup_24h": paper_24h,
        "dry_price_rows_7d": len(dry_price_rows),
        "recommendations": recommendations,
        "historical_real_rows_7d": sum(row.get("mode") == "real" for row in last_7d),
    }


def render_report(review: Dict[str, Any]) -> str:
    today = review["generated_at"]
    day = review["last_24h"]
    week = review["last_7d"]
    followup = review["paper_followup_24h"]
    errors = ", ".join(
        f"{name}: {count}" for name, count in sorted(day["dry_error_categories"].items())
    ) or "nenhuma"
    if followup["completed_windows"]:
        mark_to_market = (
            f"{followup['completed_windows']} janela(s) completa(s); "
            f"MFE médio {followup['avg_mfe_pct']:.3f}%, "
            f"MAE médio {followup['avg_mae_pct']:.3f}%"
        )
    else:
        mark_to_market = "sem janelas de 24h completas"

    lines = [
        f"# Revisão automática do dry-run ({today})",
        "",
        f"Modo atual: **{review['current_mode']}**",
        f"Últimas 24h: {day['dry_cycles']} ciclos dry, {day['dry_entries']} entrada(s) simulada(s), {day['dry_errors']} erro(s).",
        f"Últimos 7 dias: {week['dry_cycles']} ciclos dry, {week['dry_entries']} entrada(s) simulada(s), {week['dry_errors']} erro(s).",
        f"Categorias de erro nas últimas 24h: {errors}.",
        f"Acompanhamento hipotético de entradas dry: {mark_to_market}.",
        f"Preços dry estruturados nos últimos 7 dias: {review['dry_price_rows_7d']}.",
        f"Registros real históricos nos últimos 7 dias (excluídos das métricas dry): {review['historical_real_rows_7d']}.",
        "",
        "## Recomendações",
    ]
    lines.extend(f"- {item}" for item in review["recommendations"])
    lines.extend([
        "",
        "Esta revisão não altera a estratégia nem envia ordens. MFE/MAE são mark-to-market hipotéticos, antes de custos, e não representam lucro realizado.",
    ])
    return "\n".join(lines) + "\n"


def telegram_summary(review: Dict[str, Any]) -> str:
    day = review["last_24h"]
    week = review["last_7d"]
    top_recommendation = review["recommendations"][0] if review["recommendations"] else "Sem alertas operacionais."
    return (
        "Satoshi: revisão diária dry-run\n"
        f"24h: {day['dry_cycles']} ciclos, {day['dry_entries']} entradas simuladas, {day['dry_errors']} erros.\n"
        f"7d: {week['dry_cycles']} ciclos, {week['dry_entries']} entradas simuladas.\n"
        f"Ação: {top_recommendation}\n"
        "Relatório detalhado salvo em logs/daily_review.md. Sem ajuste automático ou ordens."
    )


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(path.name + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    os.replace(temporary_path, path)


def run_daily_review_if_due(
    log_path: str,
    output_path: str,
    state_path: str,
    current_mode: str,
    notifier: Optional[Callable[[str], None]] = None,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    now = now or datetime.now()
    review_date = now.date().isoformat()
    state_file = Path(state_path)
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    if state.get("last_review_date") == review_date:
        return None

    review = build_review(load_log_rows(log_path), current_mode=current_mode, now=now)
    _atomic_write(Path(output_path), render_report(review))
    _atomic_write(state_file, json.dumps({"last_review_date": review_date}, indent=2) + "\n")
    if notifier is not None:
        notifier(telegram_summary(review))
    return review


if __name__ == "__main__":
    from .config import get_trading_mode

    current_directory = Path.cwd()
    report = build_review(
        load_log_rows(str(current_directory / "logs" / "satoshi_log.jsonl")),
        current_mode=get_trading_mode(),
    )
    print(render_report(report), end="")