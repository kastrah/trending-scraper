#!/usr/bin/env python3
"""Extract platform session cookies from Chrome debug profile via CDP and
write them to ~/.hermes/.env so both local and VPS scrapers pick them up.

Usage:
    python3 scripts/extract_cookies.py [--cdp-port 9222] [--dry-run]

Requires Chrome to be running with --remote-debugging-port=9222.
Run scripts/launch_chrome_debug.sh first if it isn't.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import requests

# ── Target cookies per platform ──────────────────────────────────────────────
# Each entry: (env_key, domain_pattern, cookie_name)
# We write the raw cookie value to the env file.
TARGETS = [
    # TikTok — msToken is what TikTokApi needs
    ("TIKTOK_MS_TOKEN",        "tiktok.com",     "msToken"),
    ("TIKTOK_SESSION_ID",      "tiktok.com",     "sessionid"),
    # X / Twitter — auth_token + ct0 together authenticate API requests
    ("X_AUTH_TOKEN",           "x.com",          "auth_token"),
    ("X_CT0",                  "x.com",          "ct0"),
    # Instagram — sessionid is the single auth cookie; csrftoken for POST requests
    ("INSTAGRAM_SESSION_ID",   "instagram.com",  "sessionid"),
    ("INSTAGRAM_DS_USER_ID",   "instagram.com",  "ds_user_id"),
    ("INSTAGRAM_CSRF_TOKEN",   "instagram.com",  "csrftoken"),
    # Reddit
    ("REDDIT_TOKEN_V2",        "reddit.com",     "token_v2"),
    ("REDDIT_SESSION",         "reddit.com",     "reddit_session"),
    # Telegram web (only useful for web-based scraping; bot token is separate)
    ("TELEGRAM_STEL_TOKEN",    "web.telegram.org", "stel_token"),
    # YouTube — SOCS bypasses GDPR consent wall; SID/HSID for authenticated requests
    ("YOUTUBE_SOCS",           "youtube.com",      "SOCS"),
    ("YOUTUBE_SID",            "youtube.com",      "SID"),
]

ENV_FILE = Path.home() / ".hermes" / ".env"


def get_cookies(cdp_port: int) -> list[dict]:
    """Fetch all cookies from a running Chrome instance via CDP."""
    base = f"http://localhost:{cdp_port}"

    # Get the first available target (usually the active tab)
    targets = requests.get(f"{base}/json", timeout=5).json()
    # Prefer a page target
    page = next(
        (t for t in targets if t.get("type") == "page"),
        targets[0] if targets else None,
    )
    if not page:
        raise RuntimeError("No CDP targets found")

    ws_url = page["webSocketDebuggerUrl"]

    import websocket  # pip install websocket-client

    ws = websocket.create_connection(ws_url, timeout=10, suppress_origin=True)

    def cdp(method, params=None):
        ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                return msg.get("result", {})

    result = cdp("Network.getAllCookies")
    ws.close()
    return result.get("cookies", [])


def match_cookie(cookies: list[dict], domain_pat: str, name: str) -> str | None:
    for c in cookies:
        if name == c.get("name") and domain_pat in c.get("domain", ""):
            return c.get("value")
    return None


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def write_env(path: Path, env: dict[str, str]) -> None:
    lines = []
    if path.exists():
        lines = path.read_text(errors="ignore").splitlines()

    updated: set[str] = set()
    out_lines: list[str] = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in env:
                out_lines.append(f"{k}={env[k]}")
                updated.add(k)
                continue
        out_lines.append(line)

    # Append new keys not previously in file
    for k, v in env.items():
        if k not in updated:
            out_lines.append(f"{k}={v}")

    path.write_text("\n".join(out_lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract platform cookies from Chrome CDP")
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--dry-run", action="store_true", help="print values, don't write")
    parser.add_argument("--env-file", default=str(ENV_FILE))
    args = parser.parse_args()

    print(f"Connecting to Chrome CDP on port {args.cdp_port}...")
    try:
        cookies = get_cookies(args.cdp_port)
    except Exception as e:
        print(f"ERROR: {e}")
        print("Make sure Chrome is running with --remote-debugging-port=9222")
        print("Run:  bash scripts/launch_chrome_debug.sh")
        sys.exit(1)

    print(f"Found {len(cookies)} cookies total\n")

    found: dict[str, str] = {}
    missing: list[str] = []

    for env_key, domain, cookie_name in TARGETS:
        val = match_cookie(cookies, domain, cookie_name)
        if val:
            display = val[:12] + "..." if len(val) > 15 else val
            print(f"  ✓  {env_key:<30}  ({domain} / {cookie_name}) = {display}")
            found[env_key] = val
        else:
            print(f"  ✗  {env_key:<30}  ({domain} / {cookie_name}) — not found")
            missing.append(env_key)

    print()
    if missing:
        print(f"Missing {len(missing)} cookies — you may not be logged into those sites.")
        print("Open Chrome (using the debug profile) and log in, then re-run this script.\n")

    if not found:
        sys.exit(1)

    env_path = Path(args.env_file)
    if args.dry_run:
        print("Dry run — not writing to env file")
        return

    write_env(env_path, found)
    print(f"Written {len(found)} values → {env_path}")
    print("\nNext: re-run your scrapers. Cookies will be picked up automatically.")


if __name__ == "__main__":
    main()
