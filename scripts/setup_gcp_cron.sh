#!/bin/bash
# Install cron jobs on a GCP VM for automated market scans and signal maintenance.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== TRADING INTELLIGENCE AUTOMATION SETUP ==="
echo "This script configures crontab jobs on this GCP VM."
echo "It runs dashboard scans first, then the signal ledger / auto-paper dry-run pipeline."
echo "Cron timezone is fixed to Asia/Bangkok."
echo "================================================"

# Dashboard scan jobs. Assumes dashboard.service exposes Flask on localhost:5050.
CRON_TH_MORN="15 10 * * 1-5 curl -s \"http://127.0.0.1:5050/api/run?market=TH\" > /dev/null 2>&1"
CRON_TH_EVE="15 16 * * 1-5 curl -s \"http://127.0.0.1:5050/api/run?market=TH\" > /dev/null 2>&1"
CRON_US_SCAN="30 20 * * 1-5 curl -s \"http://127.0.0.1:5050/api/run?market=US\" > /dev/null 2>&1"

# Follow-up signal pipeline jobs. These ingest reports, update outcomes, and run auto-paper dry-run.
CRON_TH_PIPE_MORN="45 10 * * 1-5 cd \"$PROJECT_ROOT\" && bash scripts/run_gcp_daily_pipeline.sh TH"
CRON_TH_PIPE_EVE="45 16 * * 1-5 cd \"$PROJECT_ROOT\" && bash scripts/run_gcp_daily_pipeline.sh TH"
CRON_US_PIPE="0 21 * * 1-5 cd \"$PROJECT_ROOT\" && bash scripts/run_gcp_daily_pipeline.sh US"

CURRENT_CRON=$(mktemp)
CLEAN_CRON=$(mktemp)

cleanup() {
    rm -f "$CURRENT_CRON" "$CLEAN_CRON"
}
trap cleanup EXIT

crontab -l > "$CURRENT_CRON" 2>/dev/null || true

# Replace the managed block and remove older unmanaged versions of these jobs.
awk '
    $0 == "# BEGIN TONG_TRADING_AUTOMATION" { skip = 1; next }
    $0 == "# END TONG_TRADING_AUTOMATION" { skip = 0; next }
    skip { next }
    /Automated Trading Intelligence Scans/ { next }
    /Automated Signal Ledger \/ Auto-paper Dry-run Pipeline/ { next }
    /api\/run\?market=(TH|US)/ { next }
    /run_gcp_daily_pipeline\.sh (TH|US)/ { next }
    { print }
' "$CURRENT_CRON" > "$CLEAN_CRON"

{
    echo ""
    echo "# BEGIN TONG_TRADING_AUTOMATION"
    echo "CRON_TZ=Asia/Bangkok"
    echo "# Automated Trading Intelligence Scans (TH Market)"
    echo "$CRON_TH_MORN"
    echo "$CRON_TH_EVE"
    echo "# Automated Signal Ledger / Auto-paper Dry-run Pipeline (TH Market)"
    echo "$CRON_TH_PIPE_MORN"
    echo "$CRON_TH_PIPE_EVE"
    echo "# Automated Trading Intelligence Scans (US Market)"
    echo "$CRON_US_SCAN"
    echo "# Automated Signal Ledger / Auto-paper Dry-run Pipeline (US Market)"
    echo "$CRON_US_PIPE"
    echo "# END TONG_TRADING_AUTOMATION"
} >> "$CLEAN_CRON"

crontab "$CLEAN_CRON"
echo "Cron jobs successfully installed or updated."
echo "Current crontab configuration:"
crontab -l
