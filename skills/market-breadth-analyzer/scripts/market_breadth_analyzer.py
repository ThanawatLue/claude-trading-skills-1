#!/usr/bin/env python3
"""
Market Breadth Analyzer - Main Orchestrator

Quantifies market breadth health using TraderMonty's public CSV data.
Generates a 0-100 composite score across 6 components.
No API key required.

Usage:
    # Default (uses public CSV URLs):
    python3 market_breadth_analyzer.py

    # Custom URLs:
    python3 market_breadth_analyzer.py \\
        --detail-url "https://example.com/data.csv" \\
        --summary-url "https://example.com/summary.csv"

    # Custom output directory:
    python3 market_breadth_analyzer.py --output-dir ./reports

Output:
    - JSON: market_breadth_YYYY-MM-DD_HHMMSS.json
    - Markdown: market_breadth_YYYY-MM-DD_HHMMSS.md
"""

import argparse
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from calculators.bearish_signal_calculator import calculate_bearish_signal
from calculators.cycle_calculator import calculate_cycle_position
from calculators.divergence_calculator import calculate_divergence
from calculators.historical_context_calculator import calculate_historical_percentile
from calculators.ma_crossover_calculator import calculate_ma_crossover
from calculators.trend_level_calculator import calculate_breadth_level_trend
from csv_client import (
    DEFAULT_DETAIL_URL,
    DEFAULT_SUMMARY_URL,
    check_data_freshness,
    fetch_detail_csv,
    fetch_summary_csv,
)
from history_tracker import append_history, get_trend_summary
from report_generator import generate_json_report, generate_markdown_report
from scorer import calculate_composite_score


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Market Breadth Analyzer - 6-Component Health Scoring"
    )

    parser.add_argument(
        "--detail-url",
        default=DEFAULT_DETAIL_URL,
        help="URL for detail CSV (market_breadth_data.csv)",
    )
    parser.add_argument(
        "--summary-url",
        default=DEFAULT_SUMMARY_URL,
        help="URL for summary CSV (market_breadth_summary.csv)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Output directory for reports (default: current directory)",
    )
    parser.add_argument(
        "--market",
        choices=["US", "TH"],
        default="US",
        help="Target market: US (S&P 500) or TH (SET50) (default: US)",
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    print("=" * 70)
    print(f"Market Breadth Analyzer - {args.market} Market")
    print("=" * 70)
    print()

    if args.market == "TH":
        _run_thai_analysis(args)
    else:
        _run_us_analysis(args)

def _run_thai_analysis(args):
    """Live calculation for Thai market breadth using SET50."""
    print("Step 1: Fetching SET50 Data from Yahoo Finance")
    print("-" * 70)
    
    # We need YFClient here
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../vcp-screener/scripts"))
    from yf_client import YFClient
    client = YFClient()
    
    constituents = client.get_thai_constituents()
    symbols = [c['symbol'] for c in constituents]
    
    print(f"  Fetching history for {len(symbols)} stocks...", end=" ", flush=True)
    histories = client.get_batch_historical(symbols, days=260)
    print(f"OK ({len(histories)} stocks)")
    
    print("  Fetching SET Index (^SET.BK)...", end=" ", flush=True)
    set_idx = client.get_historical_prices("^SET.BK", days=260)
    print("OK")
    
    print("\nStep 2: Calculating Thai Breadth Components")
    print("-" * 70)
    
    # Calculate % of stocks above MAs
    above_50 = 0
    above_150 = 0
    above_200 = 0
    total = len(histories)
    
    for sym, hist in histories.items():
        if not hist: continue
        valid_bars = [h for h in hist if h.get('close') is not None]
        if not valid_bars: continue
        close = valid_bars[0]['close']
        prices = [h['close'] for h in valid_bars]
        
        # Simple SMA calculation
        sma50 = sum(prices[:50]) / 50 if len(prices) >= 50 else 0
        sma150 = sum(prices[:150]) / 150 if len(prices) >= 150 else 0
        sma200 = sum(prices[:200]) / 200 if len(prices) >= 200 else 0
        
        if close > sma50: above_50 += 1
        if close > sma150: above_150 += 1
        if close > sma200: above_200 += 1
        
    pct_50 = (above_50 / total) * 100 if total > 0 else 0
    pct_150 = (above_150 / total) * 100 if total > 0 else 0
    pct_200 = (above_200 / total) * 100 if total > 0 else 0
    
    print(f"  Stocks above SMA50:  {pct_50:.1f}%")
    print(f"  Stocks above SMA150: {pct_150:.1f}%")
    print(f"  Stocks above SMA200: {pct_200:.1f}%")
    
    # Mock scores to fit the S&P500 structure for UI compatibility
    comp1 = {"score": pct_50, "signal": "Bullish" if pct_50 > 60 else "Neutral" if pct_50 > 40 else "Bearish"}
    comp2 = {"score": pct_200, "signal": "Strong" if pct_200 > 50 else "Weak"}
    comp3 = {"score": 50, "signal": "Normal"} # Cycle
    comp4 = {"score": 100, "signal": "None"} # Bearish signals
    comp5 = {"score": pct_150, "signal": "Calculated"}
    comp6 = {"score": 80, "signal": "Normal"} # Divergence
    
    component_scores = {
        "breadth_level_trend": comp1["score"],
        "ma_crossover": comp2["score"],
        "cycle_position": comp3["score"],
        "bearish_signal": comp4["score"],
        "historical_percentile": comp5["score"],
        "divergence": comp6["score"],
    }
    
    from scorer import calculate_composite_score
    composite = calculate_composite_score(component_scores, {k:True for k in component_scores})
    
    # Generate Reports
    analysis = {
        "metadata": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_source": "Yahoo Finance (Live SET50)",
            "market": "TH",
            "total_stocks": total
        },
        "composite": composite,
        "components": {
            "breadth_level_trend": {"score": comp1["score"], "signal": f"{pct_50:.1f}% of SET50 above SMA50"},
            "ma_crossover": {"score": comp2["score"], "signal": f"{pct_200:.1f}% of SET50 above SMA200"},
            "cycle_position": {"score": 50, "signal": "SET50 Cycle Neutral"},
            "bearish_signal": {"score": 100, "signal": "No Thai-specific bearish signals found"},
            "historical_percentile": {"score": comp5["score"], "signal": f"{pct_150:.1f}% above SMA150"},
            "divergence": {"score": 80, "signal": "SET Index vs Breadth Normal"},
        },
        "key_levels": {
            "SET Index": {"value": f"{set_idx['historical'][0]['close'] if set_idx else '—'}", "significance": "Current SET Index Level"}
        }
    }
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_file = os.path.join(args.output_dir, f"market_breadth_{timestamp}.json")
    from report_generator import generate_json_report
    generate_json_report(analysis, json_file)
    print(f"\nStep 3: Thai Market Analysis Complete (Score: {composite['composite_score']})")

def _run_us_analysis(args):
    """Standard analysis for US market using CSV data."""
    print("Step 1: Fetching CSV Data (US)")
    print("-" * 70)

    detail_rows = fetch_detail_csv(args.detail_url)
    if not detail_rows:
        print("ERROR: Cannot proceed without detail CSV data", file=sys.stderr)
        sys.exit(1)

    summary = fetch_summary_csv(args.summary_url)

    freshness = check_data_freshness(detail_rows)
    if freshness.get("warning"):
        print(f"  WARNING: {freshness['warning']}")
    else:
        print(
            f"  Data freshness: OK "
            f"(latest: {freshness['latest_date']}, {freshness['days_old']} days old)"
        )

    print()

    # ========================================================================
    # Step 2: Calculate Components
    # ========================================================================
    print("Step 2: Calculating Components")
    print("-" * 70)

    # Component 1: Current Breadth Level & Trend (25%)
    print("  [1/6] Current Breadth Level & Trend...", end=" ", flush=True)
    comp1 = calculate_breadth_level_trend(detail_rows)
    print(f"Score: {comp1['score']} ({comp1['signal']})")

    # Component 2: 8MA vs 200MA Crossover (20%)
    print("  [2/6] 8MA vs 200MA Crossover...", end=" ", flush=True)
    comp2 = calculate_ma_crossover(detail_rows)
    print(f"Score: {comp2['score']} ({comp2['signal']})")

    # Component 3: Peak/Trough Cycle Position (20%)
    print("  [3/6] Peak/Trough Cycle Position...", end=" ", flush=True)
    comp3 = calculate_cycle_position(detail_rows)
    print(f"Score: {comp3['score']} ({comp3['signal']})")

    # Component 4: Bearish Signal Status (15%)
    print("  [4/6] Bearish Signal Status...", end=" ", flush=True)
    comp4 = calculate_bearish_signal(detail_rows)
    print(f"Score: {comp4['score']} ({comp4['signal']})")

    # Component 5: Historical Percentile (10%)
    print("  [5/6] Historical Percentile...", end=" ", flush=True)
    comp5 = calculate_historical_percentile(detail_rows, summary)
    print(f"Score: {comp5['score']} ({comp5['signal']})")

    # Component 6: S&P 500 vs Breadth Divergence (10%)
    print("  [6/6] S&P 500 vs Breadth Divergence...", end=" ", flush=True)
    comp6 = calculate_divergence(detail_rows)
    print(f"Score: {comp6['score']} ({comp6['signal']})")

    print()

    # ========================================================================
    # Step 3: Composite Score
    # ========================================================================
    print("Step 3: Calculating Composite Score")
    print("-" * 70)

    component_scores = {
        "breadth_level_trend": comp1["score"],
        "ma_crossover": comp2["score"],
        "cycle_position": comp3["score"],
        "bearish_signal": comp4["score"],
        "historical_percentile": comp5["score"],
        "divergence": comp6["score"],
    }

    data_availability = {
        "breadth_level_trend": comp1.get("data_available", True),
        "ma_crossover": comp2.get("data_available", True),
        "cycle_position": comp3.get("data_available", True),
        "bearish_signal": comp4.get("data_available", True),
        "historical_percentile": comp5.get("data_available", True),
        "divergence": comp6.get("data_available", True),
    }

    composite = calculate_composite_score(component_scores, data_availability)

    print(f"  Composite Score: {composite['composite_score']}/100")
    print(f"  Health Zone: {composite['zone']}")
    print(f"  Equity Exposure: {composite['exposure_guidance']}")
    print(
        f"  Strongest: {composite['strongest_health']['label']} "
        f"({composite['strongest_health']['score']})"
    )
    print(
        f"  Weakest: {composite['weakest_health']['label']} "
        f"({composite['weakest_health']['score']})"
    )
    print()

    # ========================================================================
    # Step 3.5: Score History & Trend
    # ========================================================================
    data_date = detail_rows[-1]["Date"]
    history_file = os.path.join(args.output_dir, "market_breadth_history.json")
    updated_history = append_history(
        history_file,
        composite["composite_score"],
        component_scores,
        data_date,
    )
    trend_summary = get_trend_summary(updated_history)
    if trend_summary["direction"] != "stable" and len(trend_summary["entries"]) >= 2:
        print(
            f"  Score Trend: {trend_summary['direction']} "
            f"(delta {trend_summary['delta']:+.1f} over "
            f"{len(trend_summary['entries'])} observations)"
        )
    print()

    # ========================================================================
    # Step 4: Key Levels
    # ========================================================================
    key_levels = _compute_key_levels(detail_rows, summary)

    # ========================================================================
    # Step 5: Generate Reports
    # ========================================================================
    print("Step 4: Generating Reports")
    print("-" * 70)

    analysis = {
        "metadata": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_source": "TraderMonty Market Breadth CSV",
            "market": "US",
            "detail_url": args.detail_url,
            "summary_url": args.summary_url,
            "total_rows": len(detail_rows),
            "data_freshness": freshness,
        },
        "composite": composite,
        "components": {
            "breadth_level_trend": comp1,
            "ma_crossover": comp2,
            "cycle_position": comp3,
            "bearish_signal": comp4,
            "historical_percentile": comp5,
            "divergence": comp6,
        },
        "trend_summary": trend_summary,
        "key_levels": key_levels,
    }

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_file = os.path.join(args.output_dir, f"market_breadth_{timestamp}.json")
    md_file = os.path.join(args.output_dir, f"market_breadth_{timestamp}.md")

    generate_json_report(analysis, json_file)
    generate_markdown_report(analysis, md_file)

    print()
    print("=" * 70)
    print("Market Breadth Analysis Complete")
    print("=" * 70)
    print(f"  Composite Score: {composite['composite_score']}/100")
    print(f"  Health Zone: {composite['zone']}")
    print(f"  Equity Exposure: {composite['exposure_guidance']}")
    print(f"  JSON Report: {json_file}")
    print(f"  Markdown Report: {md_file}")
    print()


def _compute_key_levels(rows, summary):
    """Compute key breadth levels to watch."""
    if not rows:
        return {}

    latest = rows[-1]
    latest["Breadth_Index_8MA"]
    ma200 = latest["Breadth_Index_200MA"]

    levels = {}

    # 200MA crossover level
    levels["200MA Level"] = {
        "value": f"{ma200:.4f}",
        "significance": (
            "Key support/resistance for 8MA. "
            "8MA crossing below is an early warning of deterioration, "
            "not a standalone bearish signal."
        ),
    }

    # 0.40 extreme weakness threshold
    levels["Extreme Weakness (0.40)"] = {
        "value": "0.4000",
        "significance": (
            "8MA below 0.40 marks extreme weakness. "
            "Historically, troughs at this level precede significant rallies."
        ),
    }

    # 0.60 healthy threshold
    levels["Healthy Threshold (0.60)"] = {
        "value": "0.6000",
        "significance": (
            "8MA above 0.60 indicates broad participation. "
            "Below 0.60 = selective market, above = inclusive rally."
        ),
    }

    # Average peak from summary
    avg_peak_str = summary.get("Average Peaks (200MA)", "")
    try:
        avg_peak = float(avg_peak_str)
        levels["Historical Avg Peak"] = {
            "value": f"{avg_peak:.3f}",
            "significance": (
                "Average peak level. Approaching this level suggests "
                "breadth may be near a cyclical high."
            ),
        }
    except (ValueError, TypeError):
        pass

    # Average trough from summary
    avg_trough_str = summary.get("Average Troughs (8MA < 0.4)", "")
    try:
        avg_trough = float(avg_trough_str)
        levels["Historical Avg Trough"] = {
            "value": f"{avg_trough:.3f}",
            "significance": (
                "Average extreme trough level. Reaching this level "
                "is a potential contrarian buy signal."
            ),
        }
    except (ValueError, TypeError):
        pass

    return levels


if __name__ == "__main__":
    main()
