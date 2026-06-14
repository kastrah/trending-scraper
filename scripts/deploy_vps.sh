#!/usr/bin/env bash
# Sync the project to the Hermes VPS and install deps there.
# The VPS already has Bright Data credentials in /root/.hermes/.env,
# which config.py picks up automatically.
set -euo pipefail

VPS="root@your-vps"   # set to your VPS hostname or IP (Tailscale, SSH alias, or public IP)
DEST="/root/trending-scraper"
SRC="$(cd "$(dirname "$0")/.." && pwd)"

rsync -az --delete \
  --exclude output/ --exclude .env --exclude __pycache__/ --exclude .venv/ \
  "$SRC/" "$VPS:$DEST/"

ssh "$VPS" "cd $DEST && python3 -m pip install -q --break-system-packages -r requirements.txt 2>/dev/null || python3 -m pip install -q -r requirements.txt"

echo "deployed -> $VPS:$DEST"
echo "run e.g.:  ssh $VPS 'cd $DEST && python3 -m trending_scraper reddit --count 25'"
