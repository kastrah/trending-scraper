#!/usr/bin/env bash
# Install the nightly cron job on the VPS.
# Run once: bash scripts/setup_cron.sh
set -euo pipefail

VPS="root@ubuntu-4gb-nbg1-1.taildc14a1.ts.net"
REMOTE_DIR="/root/trending-scraper"

ssh "$VPS" bash <<'REMOTE'
set -euo pipefail
chmod +x /root/trending-scraper/scripts/cron_scrape.sh

# Add cron job at 05:00 UTC daily if not already there
CRON_LINE="0 5 * * * /root/trending-scraper/scripts/cron_scrape.sh"
( crontab -l 2>/dev/null | grep -v "cron_scrape.sh"; echo "$CRON_LINE" ) | crontab -

echo "Cron installed:"
crontab -l | grep cron_scrape
REMOTE

echo "Done. VPS will scrape nightly at 05:00 UTC."
