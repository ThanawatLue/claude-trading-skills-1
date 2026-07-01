"""Auto-paper qualifying ledger signals.

This script opens simulated paper positions only. It never submits broker orders.
Signals must be recent, have an entry price, pass a score threshold, and not
already have an open paper position or prior signal-paper link.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import signal_ledger

PAPER_SCRIPT_DIR = PROJECT_ROOT / "skills" / "paper-trade-simulator" / "scripts"
if str(PAPER_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(PAPER_SCRIPT_DIR))

from paper_trade import open_position  # noqa: E402


@dataclass(frozen=True)
class AutoPaperConfig:
    market: str | None = None
    min_score: float = 70.0
    max_age_days: int = 10
    max_new_positions: int = 3
    shares: int = 100
    derive_missing_risk: bool = True
    default_stop_pct: float = 8.0
    target_r: float = 2.0
    as_of: date | None = None
    dry_run: bool = True


def _as_of(config: AutoPaperConfig) -> date:
    return config.as_of or date.today()


def _open_symbols(conn: sqlite3.Connection, market: str | None = None) -> set[str]:
    where = "WHERE status = 'open'"
    params: list[Any] = []
    if market:
        where += " AND market = ?"
        params.append(market.upper())
    try:
        rows = conn.execute(f"SELECT symbol FROM paper_trade {where}", params).fetchall()
    except sqlite3.OperationalError:
        return set()
    return {r["symbol"].upper() for r in rows}


def _linked_signals(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT signal_id FROM signal_paper_link").fetchall()
    return {r["signal_id"] for r in rows}


def _derive_prices(
    signal: sqlite3.Row, config: AutoPaperConfig
) -> tuple[float, float, float] | None:
    entry = signal["entry_price"]
    if entry is None or entry <= 0:
        return None
    stop = signal["stop_price"]
    target = signal["target_price"]
    if (stop is None or target is None) and config.derive_missing_risk:
        risk = entry * (config.default_stop_pct / 100.0)
        stop = entry - risk
        target = entry + (risk * config.target_r)
    if stop is None or target is None:
        return None
    if not (0 < stop < entry < target):
        return None
    return float(entry), float(stop), float(target)


def eligible_signals(conn: sqlite3.Connection, config: AutoPaperConfig) -> list[dict[str, Any]]:
    cutoff = _as_of(config) - timedelta(days=config.max_age_days)
    where = ["raw_score >= ?", "signal_date >= ?"]
    params: list[Any] = [config.min_score, cutoff.isoformat()]
    if config.market:
        where.append("market = ?")
        params.append(config.market.upper())

    rows = conn.execute(
        f"""SELECT *
            FROM signal_ledger
            WHERE {" AND ".join(where)}
            ORDER BY raw_score DESC, signal_date DESC""",
        params,
    ).fetchall()
    open_symbols = _open_symbols(conn, config.market)
    linked = _linked_signals(conn)

    out = []
    for row in rows:
        if row["signal_id"] in linked:
            continue
        if row["symbol"].upper() in open_symbols:
            continue
        prices = _derive_prices(row, config)
        if prices is None:
            continue
        entry, stop, target = prices
        out.append(
            {
                "signal_id": row["signal_id"],
                "symbol": row["symbol"],
                "market": row["market"],
                "source_skill": row["source_skill"],
                "raw_score": row["raw_score"],
                "signal_date": row["signal_date"],
                "entry": round(entry, 4),
                "stop": round(stop, 4),
                "target": round(target, 4),
                "shares": config.shares,
            }
        )
    return out[: config.max_new_positions]


def link_signal_to_paper(
    conn: sqlite3.Connection, signal_id: str, paper_trade_id: int, mode: str = "auto"
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO signal_paper_link
           (signal_id, paper_trade_id, opened_at, mode)
           VALUES (?,?,?,?)""",
        (
            signal_id,
            paper_trade_id,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            mode,
        ),
    )
    conn.commit()


def run_auto_paper(
    conn: sqlite3.Connection,
    config: AutoPaperConfig,
    open_fn: Callable[..., dict[str, Any]] = open_position,
) -> dict[str, Any]:
    candidates = eligible_signals(conn, config)
    opened = []
    for candidate in candidates:
        if config.dry_run:
            continue
        row = open_fn(
            symbol=candidate["symbol"],
            market=candidate["market"],
            shares=int(candidate["shares"]),
            entry=float(candidate["entry"]),
            stop=float(candidate["stop"]),
            target=float(candidate["target"]),
            side="long",
            source=candidate["source_skill"],
            source_score=candidate["raw_score"],
            notes=(
                "AUTO-PAPER from signal ledger "
                f"{candidate['signal_id']} | signal_date={candidate['signal_date']}"
            ),
            emotion="calm",
        )
        link_signal_to_paper(conn, candidate["signal_id"], int(row["id"]))
        opened.append({"signal_id": candidate["signal_id"], "paper_trade_id": row["id"]})

    return {
        "dry_run": config.dry_run,
        "eligible": len(candidates),
        "opened": len(opened),
        "candidates": candidates,
        "opened_links": opened,
        "config": {
            "market": config.market,
            "min_score": config.min_score,
            "max_age_days": config.max_age_days,
            "max_new_positions": config.max_new_positions,
            "shares": config.shares,
            "derive_missing_risk": config.derive_missing_risk,
            "default_stop_pct": config.default_stop_pct,
            "target_r": config.target_r,
            "as_of": _as_of(config).isoformat(),
        },
    }


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-open paper trades from signal ledger")
    parser.add_argument("--db-path", default=str(signal_ledger.DEFAULT_DB_PATH))
    parser.add_argument("--market", choices=["US", "TH"])
    parser.add_argument("--min-score", type=float, default=70.0)
    parser.add_argument("--max-age-days", type=int, default=10)
    parser.add_argument("--max-new-positions", type=int, default=3)
    parser.add_argument("--shares", type=int, default=100)
    parser.add_argument("--default-stop-pct", type=float, default=8.0)
    parser.add_argument("--target-r", type=float, default=2.0)
    parser.add_argument("--as-of")
    parser.add_argument("--execute", action="store_true", help="Actually open paper positions")
    parser.add_argument(
        "--require-explicit-risk",
        action="store_true",
        help="Skip signals missing stop/target instead of deriving default risk.",
    )
    args = parser.parse_args(argv)

    config = AutoPaperConfig(
        market=args.market,
        min_score=args.min_score,
        max_age_days=args.max_age_days,
        max_new_positions=args.max_new_positions,
        shares=args.shares,
        derive_missing_risk=not args.require_explicit_risk,
        default_stop_pct=args.default_stop_pct,
        target_r=args.target_r,
        as_of=date.fromisoformat(args.as_of) if args.as_of else None,
        dry_run=not args.execute,
    )
    with signal_ledger.connect(args.db_path) as conn:
        result = run_auto_paper(conn, config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
