#!/usr/bin/env bash
# Nightly scrape of all platforms. Installed by setup_cron.sh — runs at 05:00 UTC.
set -uo pipefail

DIR="/root/trending-scraper"
LOG_DIR="$DIR/logs"
LOG="$LOG_DIR/cron_$(date -u +%Y-%m-%d).log"
PYTHON="python3"

mkdir -p "$LOG_DIR"
exec >> "$LOG" 2>&1

echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) starting scrape ==="

cd "$DIR"

FAILED=""

run() {
  local label="$*"
  echo "--- $label ---"
  if ! $PYTHON -m trending_scraper "$@"; then
    echo "FAILED: $label"
    FAILED="${FAILED}${label}\n"
  fi
}

# ── Platforms ────────────────────────────────────────────────────────────────
run hn         --count 30
run reddit     --count 50
run reddit     --subreddit Nigeria       --count 30
run reddit     --subreddit pharmacy      --count 30
run reddit     --subreddit Health        --count 30
run reddit     --subreddit africa        --count 30
run xtrends    --region worldwide
run xtrends    --region nigeria
run xtrends    --region united-states
run xtrends    --region united-kingdom
run telegram   --channel durov
run xuser      --username sama naval elonmusk
run instagram  --hashtag pharmacy        --count 30
run instagram  --hashtag health          --count 30
run instagram  --hashtag diabetes        --count 30
run youtube    --region nigeria          --count 50
run youtube    --region nigeria  --health --count 50

# ── Alert on any failures ────────────────────────────────────────────────────
if [[ -n "$FAILED" ]]; then
  $PYTHON - <<PYEOF
from trending_scraper.notify import alert
alert("cron failures", r"""$FAILED""")
PYEOF
fi

# ── Daily summary ────────────────────────────────────────────────────────────
$PYTHON - <<'PYEOF'
import sqlite3, pathlib, json
from trending_scraper.notify import summary
from trending_scraper.storage import OUTPUT_DIR
from datetime import datetime, timezone

day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
db = OUTPUT_DIR / f"trending_{day}.db"
if db.exists():
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT platform, COUNT(*) FROM items GROUP BY platform").fetchall()
    summary(dict(rows))
PYEOF

echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) done ==="
