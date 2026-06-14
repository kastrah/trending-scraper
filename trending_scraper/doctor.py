"""Health check for all scrapers and credentials.

Run with:  python -m trending_scraper doctor
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from . import config


@dataclass
class Check:
    name: str
    status: str   # ok | warn | error
    detail: str


def _hn() -> Check:
    return Check("hackernews", "ok", "free Firebase API — no auth needed")


def _reddit() -> Check:
    if config.get("REDDIT_TOKEN_V2"):
        return Check("reddit", "ok", "REDDIT_TOKEN_V2 set (browser cookie, tier 1)")
    if config.get("REDDIT_CLIENT_ID") and config.get("REDDIT_SECRET"):
        return Check("reddit", "ok", "OAuth client credentials set (tier 2)")
    if config.get("BRIGHT_DATA_API_KEY"):
        return Check("reddit", "warn", "no Reddit auth — pass --brightdata for Bright Data fallback")
    return Check("reddit", "error",
                 "no auth: run scripts/extract_cookies.py or set REDDIT_CLIENT_ID+REDDIT_SECRET")


def _x() -> Check:
    bd = bool(config.get("BRIGHT_DATA_API_KEY"))
    if bd:
        return Check("x", "ok", "syndication API (no auth) for timelines; Bright Data for trends")
    return Check("x", "warn",
                 "syndication API ok for timelines; trends may get blocked without Bright Data")


def _instagram() -> Check:
    if config.get("INSTAGRAM_SESSION_ID"):
        csrf = config.get("INSTAGRAM_CSRF_TOKEN")
        if csrf:
            return Check("instagram", "ok", "session + CSRF token set")
        return Check("instagram", "warn",
                     "INSTAGRAM_SESSION_ID set but INSTAGRAM_CSRF_TOKEN missing — POST may fail")
    return Check("instagram", "error",
                 "INSTAGRAM_SESSION_ID not set — run scripts/extract_cookies.py")


def _youtube() -> Check:
    if config.get("YOUTUBE_API_KEY"):
        return Check("youtube", "ok", "YOUTUBE_API_KEY set (Data API v3, tier 1)")
    ytdlp = shutil.which("yt-dlp")
    if ytdlp:
        try:
            r = subprocess.run([ytdlp, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                ver = r.stdout.decode().strip()
                return Check("youtube", "warn", f"no API key — yt-dlp search fallback ({ver})")
        except Exception:
            pass
    return Check("youtube", "error",
                 "no YOUTUBE_API_KEY and yt-dlp not found — install: brew install yt-dlp")


def _tiktok() -> Check:
    has_token = bool(config.get("TIKTOK_MS_TOKEN") or config.get("TIKTOK_SESSION_ID"))
    try:
        r = subprocess.run(
            ["python3", "-c", "from playwright.sync_api import sync_playwright"],
            capture_output=True, timeout=10,
        )
        has_playwright = r.returncode == 0
    except Exception:
        has_playwright = False

    if not has_playwright:
        return Check("tiktok", "error",
                     "Playwright not installed: pip install playwright && playwright install chromium")
    if not has_token:
        return Check("tiktok", "warn",
                     "Playwright ok but TIKTOK_MS_TOKEN not set — run scripts/extract_cookies.py")
    return Check("tiktok", "ok", "Playwright ok + ms_token set")


def _telegram() -> Check:
    bot_token = config.get("TELEGRAM_BOT_TOKEN")
    chat_id = config.get("TELEGRAM_CHAT_ID")
    if bot_token and chat_id:
        return Check("telegram", "ok", "public channel scraping ok + bot alerts configured")
    missing = [k for k, v in [("TELEGRAM_BOT_TOKEN", bot_token), ("TELEGRAM_CHAT_ID", chat_id)] if not v]
    return Check("telegram", "warn",
                 f"public channel scraping ok; alerts disabled (missing: {', '.join(missing)})")


def _brightdata() -> Check:
    api_key, zone = config.brightdata_credentials()
    if api_key:
        return Check("brightdata", "ok", f"API key set (zone: {zone})")
    return Check("brightdata", "warn",
                 "not configured — scrapers fall back to direct requests (may hit bot walls)")


def run_doctor() -> bool:
    """Print a health report for all platforms. Returns True if no errors found."""
    checks = [
        _hn(),
        _reddit(),
        _x(),
        _instagram(),
        _youtube(),
        _tiktok(),
        _telegram(),
        _brightdata(),
    ]

    icons  = {"ok": "✓", "warn": "~", "error": "✗"}
    labels = {"ok": "ok  ", "warn": "warn", "error": "ERR "}
    has_error = False

    print("trending-scraper health check\n")
    for c in checks:
        print(f"  {icons[c.status]} [{labels[c.status]}]  {c.name:<12}  {c.detail}")
        if c.status == "error":
            has_error = True

    print()
    if has_error:
        print("Fix errors before running cron. Warnings are non-fatal fallbacks.")
    else:
        print("All checks passed (warnings are non-fatal).")
    return not has_error
