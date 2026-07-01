from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from scripts import auto_paper, signal_ledger


def _register(
    conn: sqlite3.Connection,
    signal_id: str = "sig_a",
    symbol: str = "AAPL",
    score: float = 80,
    signal_date: str = "2026-07-01",
    entry: float = 100,
    stop: float | None = None,
    target: float | None = None,
) -> None:
    signal_ledger.register_signal(
        conn,
        signal_ledger.SignalRecord(
            signal_id=signal_id,
            symbol=symbol,
            market="US",
            source_skill="vcp-screener",
            signal_date=signal_date,
            raw_score=score,
            entry_price=entry,
            stop_price=stop,
            target_price=target,
        ),
    )


def test_eligible_signals_derives_missing_risk(tmp_path: Path) -> None:
    with signal_ledger.connect(tmp_path / "db.sqlite") as conn:
        _register(conn)
        config = auto_paper.AutoPaperConfig(
            market="US", min_score=70, as_of=date(2026, 7, 1), dry_run=True
        )

        candidates = auto_paper.eligible_signals(conn, config)

    assert len(candidates) == 1
    assert candidates[0]["entry"] == 100
    assert candidates[0]["stop"] == 92
    assert candidates[0]["target"] == 116


def test_run_auto_paper_dry_run_does_not_open(tmp_path: Path) -> None:
    calls = []

    def fake_open(**kwargs):
        calls.append(kwargs)
        return {"id": 123}

    with signal_ledger.connect(tmp_path / "db.sqlite") as conn:
        _register(conn)
        config = auto_paper.AutoPaperConfig(
            market="US", min_score=70, as_of=date(2026, 7, 1), dry_run=True
        )
        result = auto_paper.run_auto_paper(conn, config, open_fn=fake_open)
        links = conn.execute("SELECT * FROM signal_paper_link").fetchall()

    assert result["eligible"] == 1
    assert result["opened"] == 0
    assert calls == []
    assert links == []


def test_run_auto_paper_execute_links_signal(tmp_path: Path) -> None:
    calls = []

    def fake_open(**kwargs):
        calls.append(kwargs)
        return {"id": 123}

    with signal_ledger.connect(tmp_path / "db.sqlite") as conn:
        _register(conn)
        config = auto_paper.AutoPaperConfig(
            market="US", min_score=70, as_of=date(2026, 7, 1), dry_run=False
        )
        result = auto_paper.run_auto_paper(conn, config, open_fn=fake_open)
        second = auto_paper.run_auto_paper(conn, config, open_fn=fake_open)
        links = conn.execute("SELECT * FROM signal_paper_link").fetchall()

    assert result["opened"] == 1
    assert second["eligible"] == 0
    assert len(calls) == 1
    assert calls[0]["symbol"] == "AAPL"
    assert calls[0]["stop"] == 92
    assert len(links) == 1
    assert links[0]["paper_trade_id"] == 123


def test_stale_signal_is_not_eligible(tmp_path: Path) -> None:
    with signal_ledger.connect(tmp_path / "db.sqlite") as conn:
        _register(conn, signal_date="2026-05-25")
        config = auto_paper.AutoPaperConfig(
            market="US", min_score=70, max_age_days=10, as_of=date(2026, 7, 1)
        )

        candidates = auto_paper.eligible_signals(conn, config)

    assert candidates == []
