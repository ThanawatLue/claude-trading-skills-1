#!/bin/bash
# Script to install cron jobs on GCP VM for automated market scans

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== TRADING INTELLIGENCE AUTOMATION SETUP ==="
echo "This script will configure crontab jobs on this GCP VM to trigger scans."
echo "Frequency: Monday to Friday at 10:15 AM and 16:15 PM."
echo "============================================"

# Define the crontab entries
# Assuming Flask is running on port 5050 locally
CRON_MORN="15 10 * * 1-5 curl -s \"http://127.0.0.1:5050/api/run?market=TH\" > /dev/null 2>&1"
CRON_EVE="15 16 * * 1-5 curl -s \"http://127.0.0.1:5050/api/run?market=TH\" > /dev/null 2>&1"

# Also add US market scan at 09:30 AM EST (which is 20:30 PM Thailand time)
CRON_US="30 20 * * 1-5 curl -s \"http://127.0.0.1:5050/api/run?market=US\" > /dev/null 2>&1"

# Temp file for editing cron
TMP_CRON=$(mktemp)

# Export current cron
crontab -l > "$TMP_CRON" 2>/dev/null || true

# Check if jobs already exist, if not append them
modified=0

if ! grep -q "api/run?market=TH" "$TMP_CRON"; then
    echo "" >> "$TMP_CRON"
    echo "# Automated Trading Intelligence Scans (TH Market)" >> "$TMP_CRON"
    echo "$CRON_MORN" >> "$TMP_CRON"
    echo "$CRON_EVE" >> "$TMP_CRON"
    modified=1
fi

if ! grep -q "api/run?market=US" "$TMP_CRON"; then
    echo "" >> "$TMP_CRON"
    echo "# Automated Trading Intelligence Scans (US Market)" >> "$TMP_CRON"
    echo "$CRON_US" >> "$TMP_CRON"
    modified=1
fi

# Apply new cron
if [ $modified -eq 1 ]; then
    crontab "$TMP_CRON"
    echo "✓ Cron jobs successfully installed!"
    echo "Current crontab configuration:"
    crontab -l
else
    echo "✓ Cron jobs are already configured in crontab."
fi

# Clean up
rm "$TMP_CRON"
