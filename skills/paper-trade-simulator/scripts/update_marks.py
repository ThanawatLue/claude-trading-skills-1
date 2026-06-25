#!/usr/bin/env python3
"""Update mark-to-market prices for all open paper positions.

For each open position:
1. Fetch latest price from yfinance
2. Update last_price, last_updated, unrealized_pnl, unrealized_r
3. Track MAE (worst price) and MFE (best price) since entry
4. If price crossed stop → auto-close with status=closed_stop
5. If price crossed target → auto-close with status=closed_target
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
import logging

sys.path.insert(0, str(Path(__file__).parent))
from paper_trade import (  # noqa: E402
    DB_PATH, _db, _now_iso, close_position,
    STATUS_OPEN, STATUS_CLOSED_STOP, STATUS_CLOSED_TARGET,
)


def _fetch_price(symbol: str) -> float | None:
    """Get latest close price via yfinance. Returns None on failure."""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        h = t.history(period="2d")
        if h.empty:
            return None
        return float(h["Close"].iloc[-1])
    except Exception as e:
        print(f"  fetch error for {symbol}: {e}", file=sys.stderr)
        return None


def update_one(row: sqlite3.Row, price: float) -> dict:
    """Update marks for one open position; auto-close if stop/target crossed."""
    side = row["side"]
    entry = row["entry_price"]
    shares = row["shares"]
    risk_per_share = (entry - row["stop_price"]) if side == "long" else (row["stop_price"] - entry)

    if side == "long":
        pnl = (price - entry) * shares
        hit_stop = price <= row["stop_price"]
        hit_target = price >= row["target_price"]
    else:
        pnl = (entry - price) * shares
        hit_stop = price >= row["stop_price"]
        hit_target = price <= row["target_price"]

    r_mult = pnl / (risk_per_share * shares) if risk_per_share > 0 else 0
    new_mae = min(row["mae"] or price, price) if side == "long" else max(row["mae"] or price, price)
    new_mfe = max(row["mfe"] or price, price) if side == "long" else min(row["mfe"] or price, price)
    days = (datetime.fromisoformat(_now_iso()).replace(tzinfo=None) - datetime.fromisoformat(row["entry_at"]).replace(tzinfo=None)).days

    # Auto-close cases (priority: stop > target because stop fires first if both crossed)
    if hit_stop:
        # Close at stop price (assume execution at stop)
        close_position(row["id"], row["stop_price"], status=STATUS_CLOSED_STOP,
                       notes=f"Auto-closed: price {price:.2f} crossed stop {row['stop_price']:.2f}")
        return {"id": row["id"], "symbol": row["symbol"], "action": "auto_closed_stop",
                "exit_price": row["stop_price"]}
    if hit_target:
        close_position(row["id"], row["target_price"], status=STATUS_CLOSED_TARGET,
                       notes=f"Auto-closed: price {price:.2f} hit target {row['target_price']:.2f}")
        return {"id": row["id"], "symbol": row["symbol"], "action": "auto_closed_target",
                "exit_price": row["target_price"]}

    # Otherwise just update marks
    with _db() as conn:
        conn.execute(
            """UPDATE paper_trade
               SET last_price=?, last_updated=?, unrealized_pnl=?, unrealized_r=?,
                   mae=?, mfe=?, days_held=?
               WHERE id=?""",
            (price, _now_iso(), pnl, r_mult, new_mae, new_mfe, days, row["id"]),
        )
    return {"id": row["id"], "symbol": row["symbol"], "action": "marked",
            "price": price, "pnl": round(pnl, 2), "r": round(r_mult, 2)}


def update_all() -> list[dict]:
    with _db() as conn:
        opens = conn.execute("SELECT * FROM paper_trade WHERE status=?",
                             (STATUS_OPEN,)).fetchall()
    if not opens:
        return []

    # Group by symbol to dedupe fetches
    unique_symbols = sorted({r["symbol"] for r in opens})
    prices: dict[str, float | None] = {}
    for sym in unique_symbols:
        prices[sym] = _fetch_price(sym)

    # TradingView fallback for Thai stocks (.BK)
    thai_failures = [
        sym for sym in unique_symbols
        if sym.upper().endswith(".BK") and prices[sym] is None
    ]
    if thai_failures:
        print(f"Attempting TradingView fallback for Thai stocks: {thai_failures}", file=sys.stderr)
        try:
            tv_path = Path(__file__).resolve().parents[3] / "skills" / "vcp-screener" / "scripts"
            # Temporarily add vcp-screener to sys.path for tv_client import
            sys.path.insert(0, str(tv_path))
            import tv_client
            
            if tv_client.is_available():
                stocks = tv_client.get_thai_stocks()
                tv_prices = {s["symbol"].upper(): s["price"] for s in stocks if "symbol" in s and "price" in s}
                for sym in thai_failures:
                    prices[sym] = tv_prices.get(sym.upper())
                    if prices[sym] is not None:
                        print(f"  Successfully fetched TV fallback price for {sym}: {prices[sym]}", file=sys.stderr)
            else:
                print("  TradingView screener is not available (is_available() returned False)", file=sys.stderr)
        except ImportError:
            logging.warning(
                "tv_client not found. TradingView fallback for Thai stocks is disabled. "
                "Ensure 'vcp-screener' skill is correctly installed if you need this functionality."
            )
        except Exception as e:
            print(f"  TradingView fallback failed: {e}", file=sys.stderr)
        finally:
            # Remove vcp-screener from sys.path
            if str(tv_path) in sys.path:
                sys.path.remove(str(tv_path))

    results = []
    for row in opens:
        price = prices.get(row["symbol"])
        if price is None:
            results.append({"id": row["id"], "symbol": row["symbol"],
                            "action": "fetch_failed"})
            continue
        results.append(update_one(row, price))
    return results


def main():
    print(f"Updating marks at {_now_iso()}...")
    out = update_all()
    print(json.dumps(out, indent=2))
    # Summary
    counts = {}
    for r in out:
        counts[r["action"]] = counts.get(r["action"], 0) + 1
    print(f"\nSummary: {counts}")


if __name__ == "__main__":
    main()
