"""Trading Intelligence Dashboard - Flask Backend"""
import glob
import json
import os
import sqlite3
import subprocess
import sys
import concurrent.futures
import threading
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf
from flask import Flask, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
ROOT_DIR = BASE_DIR  # market breadth files land here
DB_PATH = os.path.join(BASE_DIR, "state", "market_cache.db")

# Subprocess environment: force UTF-8 I/O so emoji/unicode in scripts don't crash on Windows
_SUBPROCESS_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

app = Flask(__name__)

# ── Report Database ────────────────────────────────────────────────────────────

_RUN_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_run (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    market  TEXT    NOT NULL,
    run_at  TEXT    NOT NULL,
    data    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_run_market_at ON analysis_run(market, run_at DESC);
"""


def _db() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=60.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_RUN_SCHEMA)
    return conn


def db_save_run(market: str, data: dict) -> str:
    """Save a full analysis snapshot to DB. Returns the run_at timestamp."""
    run_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with _db() as conn:
        conn.execute(
            "INSERT INTO analysis_run (market, run_at, data) VALUES (?,?,?)",
            (market, run_at, json.dumps(data, ensure_ascii=False)),
        )
    return run_at


def db_load_run(market: str, at: str | None = None) -> dict | None:
    """Load a snapshot: latest if at=None, specific timestamp otherwise."""
    with _db() as conn:
        if at:
            row = conn.execute(
                "SELECT data FROM analysis_run WHERE market=? AND run_at=? LIMIT 1",
                (market, at),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT data FROM analysis_run WHERE market=? ORDER BY run_at DESC LIMIT 1",
                (market,),
            ).fetchone()
    return json.loads(row["data"]) if row else None


def db_list_runs(market: str, limit: int = 50) -> list[str]:
    """Return list of run timestamps for a market, newest first."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT run_at FROM analysis_run WHERE market=? ORDER BY run_at DESC LIMIT ?",
            (market, limit),
        ).fetchall()
    return [r["run_at"] for r in rows]


# ── File helpers (fallback when DB has no data yet) ───────────────────────────

def latest_file(pattern: str, market: str = "US") -> str | None:
    files = sorted(glob.glob(pattern), reverse=True)
    if not files:
        return None
    for f in files:
        try:
            with open(f, encoding="utf-8") as j:
                data = json.load(j)
                if isinstance(data, list):
                    return f if market == "US" else None
                if data.get("metadata", {}).get("market", "US") == market:
                    return f
        except Exception:
            continue
    return None


def latest_file_any(pattern: str) -> str | None:
    files = sorted(glob.glob(pattern), reverse=True)
    return files[0] if files else None


def load_json(path: str) -> dict | list | None:
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _collect_snapshot(market: str) -> dict:
    """Read all latest JSON files and build a snapshot dict."""
    breadth = load_json(latest_file(
        os.path.join(ROOT_DIR, "market_breadth_20[0-9][0-9]-*.json"), market))
    vcp = load_json(latest_file(
        os.path.join(REPORTS_DIR, "vcp_screener_*.json"), market))
    exposure = load_json(latest_file(
        os.path.join(REPORTS_DIR, "exposure_posture_*.json"), market))
    ibd = load_json(latest_file_any(
        os.path.join(REPORTS_DIR, "ibd_distribution_day_monitor_*.json")))
    earnings_trade = load_json(latest_file_any(
        os.path.join(REPORTS_DIR, "earnings_trade_*.json")))
    breakout_plan = load_json(latest_file_any(
        os.path.join(REPORTS_DIR, "breakout_trade_plan_*.json")))
    uptrend = load_json(latest_file_any(
        os.path.join(REPORTS_DIR, "uptrend_analysis_*.json")))
    downtrend = load_json(latest_file_any(
        os.path.join(REPORTS_DIR, "downtrend_analysis_*.json")))
    canslim = load_json(latest_file_any(
        os.path.join(REPORTS_DIR, "canslim_screener_*.json")))
    return {
        "market": market,
        "breadth": breadth,
        "vcp": vcp,
        "exposure": exposure,
        "ibd": ibd,
        "earnings_trade": earnings_trade,
        "breakout_plan": breakout_plan,
        "uptrend": uptrend,
        "downtrend": downtrend,
        "canslim": canslim,
    }


def cleanup_old_files(keep_count: int = 2):
    """Keep only the latest keep_count files matching each analysis output pattern."""
    patterns = [
        # Root directory patterns
        os.path.join(ROOT_DIR, "market_breadth_20[0-9][0-9]-*.json"),
        os.path.join(ROOT_DIR, "market_breadth_20[0-9][0-9]-*.md"),
        # Reports directory patterns
        os.path.join(REPORTS_DIR, "vcp_screener_*.json"),
        os.path.join(REPORTS_DIR, "vcp_screener_*.md"),
        os.path.join(REPORTS_DIR, "exposure_posture_*.json"),
        os.path.join(REPORTS_DIR, "exposure_posture_*.md"),
        os.path.join(REPORTS_DIR, "ibd_distribution_day_monitor_*.json"),
        os.path.join(REPORTS_DIR, "ibd_distribution_day_monitor_*.md"),
        os.path.join(REPORTS_DIR, "earnings_trade_*.json"),
        os.path.join(REPORTS_DIR, "earnings_trade_*.md"),
        os.path.join(REPORTS_DIR, "breakout_trade_plan_*.json"),
        os.path.join(REPORTS_DIR, "breakout_trade_plan_*.md"),
        os.path.join(REPORTS_DIR, "uptrend_analysis_*.json"),
        os.path.join(REPORTS_DIR, "uptrend_analysis_*.md"),
        os.path.join(REPORTS_DIR, "downtrend_analysis_*.json"),
        os.path.join(REPORTS_DIR, "downtrend_analysis_*.md"),
        os.path.join(REPORTS_DIR, "canslim_screener_*.json"),
        os.path.join(REPORTS_DIR, "canslim_screener_*.md"),
        os.path.join(REPORTS_DIR, "skill_review_*.json"),
        os.path.join(REPORTS_DIR, "skill_review_*.md"),
    ]
    for pattern in patterns:
        files = sorted(glob.glob(pattern), reverse=True)
        if len(files) > keep_count:
            for f in files[keep_count:]:
                try:
                    os.remove(f)
                except Exception as e:
                    print(f"Error removing {f}: {e}", file=sys.stderr)


def clean_unsuccessful_db_runs():
    """Scan SQLite analysis_run table and remove runs that are unsuccessful or incomplete."""
    try:
        db_path = DB_PATH
        if not os.path.exists(db_path):
            return
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        rows = cursor.execute("SELECT id, market, run_at, data FROM analysis_run").fetchall()
        to_delete = []
        
        for row in rows:
            run_id = row["id"]
            try:
                data = json.loads(row["data"])
            except Exception:
                to_delete.append(run_id)
                continue
                
            breadth = data.get("breadth")
            vcp = data.get("vcp")
            exposure = data.get("exposure")
            
            is_unsuccessful = False
            if not breadth or not isinstance(breadth, dict) or not breadth.get("composite"):
                is_unsuccessful = True
            elif not vcp or not isinstance(vcp, dict):
                is_unsuccessful = True
            elif not exposure or not isinstance(exposure, dict) or not exposure.get("recommendation"):
                is_unsuccessful = True
                
            if is_unsuccessful:
                to_delete.append(run_id)
                
        if to_delete:
            cursor.execute(
                f"DELETE FROM analysis_run WHERE id IN ({','.join(map(str, to_delete))})"
            )
            conn.commit()
            print(f"Cleaned up {len(to_delete)} unsuccessful/incomplete runs from database.", file=sys.stderr)
            
        conn.close()
    except Exception as e:
        print(f"Error during DB cleaning: {e}", file=sys.stderr)


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/data")
def api_data():
    market = request.args.get("market", "US").upper()
    at = request.args.get("at")  # optional ISO timestamp for historical view

    if at:
        # Historical view: only DB (no fallback to files)
        snapshot = db_load_run(market, at)
        if not snapshot:
            return jsonify({"error": f"No data for {market} at {at}"}), 404
        return jsonify(snapshot)

    # Live view: try DB first, fallback to JSON files for first-run
    snapshot = db_load_run(market)
    if snapshot:
        return jsonify(snapshot)

    snapshot = _collect_snapshot(market)
    return jsonify(snapshot)


@app.route("/api/runs")
def api_runs():
    """List past run timestamps for a market."""
    market = request.args.get("market", "US").upper()
    limit = int(request.args.get("limit", 50))
    runs = db_list_runs(market, limit)
    return jsonify({"market": market, "runs": runs})


@app.route("/api/run")
def api_run():
    """Re-run analysis scripts for a specific market, then snapshot to DB."""
    market = request.args.get("market", "US").upper()
    account_size = request.args.get("account_size", "50000")
    risk_pct = request.args.get("risk_pct", "0.5")
    target_r = request.args.get("target_r", "2.0")

    log = []

    def _run(cmd, timeout=300, extra_env=None):
        env = {**_SUBPROCESS_ENV, **(extra_env or {})}
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", cwd=BASE_DIR, timeout=timeout, env=env)
            return {"cmd": os.path.basename(cmd[1]), "ok": r.returncode == 0,
                    "out": r.stdout[-1000:], "err": r.stderr[-1500:]}
        except subprocess.TimeoutExpired:
            return {"cmd": os.path.basename(cmd[1]), "ok": False,
                    "out": "", "err": f"Timeout after {timeout}s"}
        except Exception as e:
            return {"cmd": os.path.basename(cmd[1]), "ok": False, "out": "", "err": str(e)}

    # ── Phase 1: Heavy Primary Scanners (Parallel Execution) ──────────────────────
    primary_tasks = [
        # 1. Market Breadth Analyzer
        ([sys.executable, os.path.join(BASE_DIR, "skills", "market-breadth-analyzer", "scripts", "market_breadth_analyzer.py"), "--market", market], 300, None),
        # 2. VCP Screener
        ([sys.executable, os.path.join(BASE_DIR, "skills", "vcp-screener", "scripts", "screen_vcp.py"), "--market", market, "--max-candidates", "50", "--top", "50"], 300, None),
        # 3. Uptrend Analyzer
        ([sys.executable, os.path.join(BASE_DIR, "skills", "uptrend-analyzer", "scripts", "uptrend_analyzer.py"), "--output-dir", REPORTS_DIR], 120, None),
        # 4. Downtrend Duration Analyzer
        ([sys.executable, os.path.join(BASE_DIR, "skills", "downtrend-duration-analyzer", "scripts", "analyze_downtrends.py"), "--max-stocks", "100", "--output-dir", REPORTS_DIR], 300, None)
    ]

    if market == "US":
        primary_tasks.extend([
            # 5. IBD Distribution Day Monitor
            ([sys.executable, os.path.join(BASE_DIR, "skills", "ibd-distribution-day-monitor", "scripts", "ibd_monitor.py"), "--output-dir", REPORTS_DIR], 60, None),
            # 6. Earnings Trade Analyzer
            ([sys.executable, os.path.join(BASE_DIR, "skills", "earnings-trade-analyzer", "scripts", "analyze_earnings_trades.py"), "--output-dir", REPORTS_DIR], 600, None),
            # 7. CANSLIM Screener
            ([sys.executable, os.path.join(BASE_DIR, "skills", "canslim-screener", "scripts", "screen_canslim.py"), "--max-candidates", "40", "--top", "40", "--output-dir", REPORTS_DIR], 300, None)
        ])

    print(f"Starting Phase 1 parallel execution with {len(primary_tasks)} independent scanners...", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(primary_tasks)) as executor:
        futures = {
            executor.submit(_run, cmd, timeout, env): cmd
            for cmd, timeout, env in primary_tasks
        }
        for future in concurrent.futures.as_completed(futures):
            log.append(future.result())

    # ── Phase 2: Dependent Planners (Parallel Execution) ─────────────────────────
    latest_mb = latest_file(os.path.join(ROOT_DIR, "market_breadth_20[0-9][0-9]-*.json"), market)
    latest_vcp = latest_file(os.path.join(REPORTS_DIR, "vcp_screener_*.json"), market)

    dependent_tasks = [
        # 1. Exposure Coach (needs fresh market breadth output)
        ([sys.executable, os.path.join(BASE_DIR, "skills", "exposure-coach", "scripts", "calculate_exposure.py"), "--breadth", latest_mb or ""], 60, None)
    ]

    if latest_vcp:
        dependent_tasks.append(
            # 2. Breakout Trade Planner (needs fresh VCP screener output)
            ([sys.executable, os.path.join(BASE_DIR, "skills", "breakout-trade-planner", "scripts", "plan_breakout_trades.py"),
              "--input", latest_vcp, "--account-size", account_size, "--risk-pct", risk_pct, "--target-r-multiple", target_r, "--output-dir", REPORTS_DIR], 60, None)
        )

    print(f"Starting Phase 2 parallel execution with {len(dependent_tasks)} dependent planners...", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(dependent_tasks)) as executor:
        futures = {
            executor.submit(_run, cmd, timeout, env): cmd
            for cmd, timeout, env in dependent_tasks
        }
        for future in concurrent.futures.as_completed(futures):
            log.append(future.result())

    if not latest_vcp:
        log.append({"cmd": "plan_breakout_trades.py", "ok": False,
                    "out": "", "err": "No VCP screener output found"})

    # Save snapshot to DB if successful
    snapshot = _collect_snapshot(market)
    
    # Verify if the run was successful (must have valid breadth and vcp data)
    breadth = snapshot.get("breadth")
    vcp = snapshot.get("vcp")
    is_success = (
        breadth and isinstance(breadth, dict) and breadth.get("composite") and
        vcp and isinstance(vcp, dict)
    )
    
    if is_success:
        run_at = db_save_run(market, snapshot)
        status = "success"
    else:
        run_at = None
        status = "failed"
        print(f"Warning: Run at {datetime.now().isoformat()} was unsuccessful and not saved to DB.", file=sys.stderr)
        
    cleanup_old_files(keep_count=2)
    clean_unsuccessful_db_runs()

    return jsonify({"status": status, "market": market, "run_at": run_at, "log": log})


@app.route("/api/history/<symbol>")
def api_history(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1y")
        if df.empty:
            return jsonify({"error": "No data found"}), 404
        df = df.reset_index()
        history = [
            {
                "time": row["Date"].strftime("%Y-%m-%d"),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "value": float(row["Volume"]),
            }
            for _, row in df.iterrows()
        ]
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/db/stats")
def api_db_stats():
    """Return DB stats: run counts, date ranges per market."""
    try:
        clean_unsuccessful_db_runs()
        with _db() as conn:
            rows = conn.execute("""
                SELECT market,
                       COUNT(*)        AS total_runs,
                       MIN(run_at)     AS oldest_run,
                       MAX(run_at)     AS newest_run
                FROM analysis_run
                GROUP BY market
                ORDER BY market
            """).fetchall()
            price_stats = conn.execute("""
                SELECT COUNT(DISTINCT symbol) AS symbols,
                       COUNT(*)               AS total_bars,
                       MIN(date)              AS oldest_bar,
                       MAX(date)              AS newest_bar
                FROM price_bar
            """).fetchone()
        return jsonify({
            "analysis_runs": [dict(r) for r in rows],
            "price_cache": dict(price_stats) if price_stats else {},
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    cleanup_old_files(keep_count=2)
    clean_unsuccessful_db_runs()
    app.run(debug=True, port=5050)
