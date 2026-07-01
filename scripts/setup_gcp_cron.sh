#!/bin/bash
# Install cron jobs on a GCP VM for automated market scans and signal maintenance.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== TRADING INTELLIGENCE AUTOMATION SETUP ==="
echo "This script configures crontab jobs on this GCP VM."
echo "It runs dashboard scans first, then the signal ledger / auto-paper dry-run pipeline."
echo "================================================"

# Dashboard scan jobs. Assumes dashboard.service exposes Flask on localhost:5050.
CRON_TH_MORN="15 10 * * 1-5 curl -s \"http://127.0.0.1:5050/api/run?market=TH\" > /dev/null 2>&1"
CRON_TH_EVE="15 16 * * 1-5 curl -s \"http://127.0.0.1:5050/api/run?market=TH\" > /dev/null 2>&1"
CRON_US_SCAN="30 20 * * 1-5 curl -s \"http://127.0.0.1:5050/api/run?market=US\" > /dev/null 2>&1"

# Follow-up signal pipeline jobs. These ingest reports, update outcomes, and run auto-paper dry-run.
CRON_TH_PIPE_MORN="45 10 * * 1-5 cd \"$PROJECT_ROOT\" && bash scripts/run_gcp_daily_pipeline.sh TH"
CRON_TH_PIPE_EVE="45 16 * * 1-5 cd \"$PROJECT_ROOT\" && bash scripts/run_gcp_daily_pipeline.sh TH"
CRON_US_PIPE="0 21 * * 1-5 cd \"$PROJECT_ROOT\" && bash scripts/run_gcp_daily_pipeline.sh US"

TMP_CRON=$(mktemp)
crontab -l > "$TMP_CRON" 2>/dev/null || true

modified=0

if ! grep -q "api/run?market=TH" "$TMP_CRON"; then
    echo "" >> "$TMP_CRON"
    echo "# Automated Trading Intelligence Scans (TH Market)" >> "$TMP_CRON"
    echo "$CRON_TH_MORN" >> "$TMP_CRON"
    echo "$CRON_TH_EVE" >> "$TMP_CRON"
    modified=1
fi

if ! grep -q "run_gcp_daily_pipeline.sh TH" "$TMP_CRON"; then
    echo "" >> "$TMP_CRON"
    echo "# Automated Signal Ledger / Auto-paper Dry-run Pipeline (TH Market)" >> "$TMP_CRON"
    echo "$CRON_TH_PIPE_MORN" >> "$TMP_CRON"
    echo "$CRON_TH_PIPE_EVE" >> "$TMP_CRON"
    modified=1
fi

if ! grep -q "api/run?market=US" "$TMP_CRON"; then
    echo "" >> "$TMP_CRON"
    echo "# Automated Trading Intelligence Scans (US Market)" >> "$TMP_CRON"
    echo "$CRON_US_SCAN" >> "$TMP_CRON"
    modified=1
fi

if ! grep -q "run_gcp_daily_pipeline.sh US" "$TMP_CRON"; then
    echo "" >> "$TMP_CRON"
    echo "# Automated Signal Ledger / Auto-paper Dry-run Pipeline (US Market)" >> "$TMP_CRON"
    echo "$CRON_US_PIPE" >> "$TMP_CRON"
    modified=1
fi

if [ "$modified" -eq 1 ]; then
    crontab "$TMP_CRON"
    echo "Cron jobs successfully installed."
    echo "Current crontab configuration:"
    crontab -l
else
    echo "Cron jobs are already configured in crontab."
fi

rm "$TMP_CRON"
