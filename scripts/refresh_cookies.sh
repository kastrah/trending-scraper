#!/usr/bin/env bash
# Extract fresh cookies from Chrome debug profile and sync to VPS.
# Safe to run anytime; Chrome must be open (launch_chrome_debug.sh if not).
#
# Install as a launchd job (runs every 6 hours):
#   bash scripts/refresh_cookies.sh --install
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(dirname "$SCRIPT_DIR")"
PYTHON="$PROJECT/.venv/bin/python"
VPS="root@ubuntu-4gb-nbg1-1.taildc14a1.ts.net"
PLIST="$HOME/Library/LaunchAgents/com.trending-scraper.refresh-cookies.plist"

if [[ "${1:-}" == "--install" ]]; then
  cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.trending-scraper.refresh-cookies</string>
  <key>ProgramArguments</key>
  <array>
    <string>$SCRIPT_DIR/refresh_cookies.sh</string>
  </array>
  <key>StartInterval</key>
  <integer>21600</integer>
  <key>StandardOutPath</key>
  <string>$HOME/.hermes/logs/refresh-cookies.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/.hermes/logs/refresh-cookies.log</string>
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
PLIST
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "Installed: will refresh cookies every 6 hours"
  exit 0
fi

# ── Main refresh logic ────────────────────────────────────────────────────────

echo "[$(date -u +%H:%M:%SZ)] Refreshing cookies..."

# Launch Chrome debug profile if not already running
if ! curl -s http://localhost:9222/json/version >/dev/null 2>&1; then
  bash "$SCRIPT_DIR/launch_chrome_debug.sh"
fi

# Extract cookies into ~/.hermes/.env
"$PYTHON" "$SCRIPT_DIR/extract_cookies.py" --env-file "$HOME/.hermes/.env"

# Sync to VPS (ignore SSH errors — VPS may be unreachable)
if ssh -o ConnectTimeout=5 "$VPS" true 2>/dev/null; then
  scp -q "$HOME/.hermes/.env" "$VPS:/root/.hermes/.env"
  echo "[$(date -u +%H:%M:%SZ)] Synced to VPS"
else
  echo "[$(date -u +%H:%M:%SZ)] VPS unreachable — skipping sync"
fi

echo "[$(date -u +%H:%M:%SZ)] Done"
