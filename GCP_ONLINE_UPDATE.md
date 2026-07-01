# GCP Online Automation Update

Last updated: 2026-07-01

## What Changed

The project already had a GCP VM deployment path through GitHub Actions. This update extends it so the VM can keep the trading workflow running even when the local computer is off.

Changed files:

- `.github/workflows/deploy.yml`
- `scripts/setup_gcp_cron.sh`
- `scripts/run_gcp_daily_pipeline.sh`

## Deployment Flow

When code is pushed to `main`, GitHub Actions now:

1. SSHs into the GCP VM.
2. Runs `git pull origin main`.
3. Runs `uv sync`.
4. Creates runtime folders:
   - `logs/`
   - `reports/daily-signal-pipeline/`
   - `state/`
5. Makes automation scripts executable.
6. Runs `bash scripts/setup_gcp_cron.sh`.
7. Restarts `dashboard.service`.

This means the VM should receive both dashboard updates and cron automation updates after a successful push.

## Cron Jobs Installed On GCP

The cron setup script now keeps the original dashboard scans and adds follow-up daily signal pipeline jobs.

TH market:

```text
10:15 Mon-Fri  scan dashboard: /api/run?market=TH
10:45 Mon-Fri  run signal pipeline: scripts/run_gcp_daily_pipeline.sh TH
16:15 Mon-Fri  scan dashboard: /api/run?market=TH
16:45 Mon-Fri  run signal pipeline: scripts/run_gcp_daily_pipeline.sh TH
```

US market:

```text
20:30 Mon-Fri  scan dashboard: /api/run?market=US
21:00 Mon-Fri  run signal pipeline: scripts/run_gcp_daily_pipeline.sh US
```

## What The Pipeline Does

The GCP pipeline runs:

```bash
uv run python scripts/run_daily_signal_pipeline.py --config state/automation_config.yaml --market <TH|US>
```

It performs:

1. Ingest thesis files.
2. Ingest signal files from configured report patterns.
3. Update forward outcomes.
4. Run auto-paper in dry-run mode by default.
5. Write daily reports.

Default config is still safe:

```yaml
auto_paper:
  enabled: true
  execute: false
```

So the VM will not open new paper positions unless `execute` is explicitly enabled.

## Logs And Reports

Pipeline logs:

```text
logs/daily_signal_pipeline_TH.log
logs/daily_signal_pipeline_US.log
```

Daily reports:

```text
reports/daily-signal-pipeline/daily_signal_pipeline_YYYY-MM-DD.json
reports/daily-signal-pipeline/daily_signal_pipeline_YYYY-MM-DD.md
```

Dashboard service logs depend on the VM's systemd setup, usually:

```bash
sudo journalctl -u dashboard.service -n 100 --no-pager
```

## One-Time VM Checks

After pushing this update, check these on the GCP VM:

```bash
cd ~/tong_trading
git pull origin main
bash scripts/setup_gcp_cron.sh
crontab -l
sudo systemctl status dashboard.service
```

Manual dry-run test:

```bash
cd ~/tong_trading
bash scripts/run_gcp_daily_pipeline.sh TH
tail -n 80 logs/daily_signal_pipeline_TH.log
```

## Required Secrets / Environment

GitHub Actions needs these repository secrets:

```text
GCP_HOST
GCP_USERNAME
GCP_SSH_KEY
```

The VM should have any required runtime environment variables for dashboard/data sync:

```text
HF_TOKEN
HF_DB_REPO_ID
FMP_API_KEY      optional/needed by some scanners
FINVIZ_API_KEY   optional
```

## Current Limitation

This update prepares unattended GCP operation, but I cannot verify the live VM from this local workspace because SSH credentials and GitHub secrets are not available here.

Verification should be done after pushing to `main` by checking GitHub Actions and VM cron logs.
