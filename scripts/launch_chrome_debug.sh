#!/usr/bin/env bash
# Launch the EXISTING Chrome debug profile on port 9222.
# Never creates a new profile — always uses ~/chrome-debug-profile/.
# Safe to run multiple times; exits early if Chrome is already on port 9222.
set -euo pipefail

PORT=9222
PROFILE="$HOME/chrome-debug-profile"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

if curl -s "http://localhost:$PORT/json/version" >/dev/null 2>&1; then
  echo "Chrome debug already running on port $PORT"
  exit 0
fi

echo "Launching Chrome with existing debug profile..."
"$CHROME" \
  --remote-debugging-port=$PORT \
  --user-data-dir="$PROFILE" \
  --no-first-run \
  --no-default-browser-check \
  --disable-background-networking \
  --disable-sync \
  &

# Wait for CDP to be ready (up to 10s)
for i in $(seq 1 20); do
  if curl -s "http://localhost:$PORT/json/version" >/dev/null 2>&1; then
    echo "Chrome CDP ready on port $PORT"
    exit 0
  fi
  sleep 0.5
done

echo "ERROR: Chrome did not start in time"
exit 1
