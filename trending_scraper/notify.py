"""Telegram notification helper — sends a message via the Hermes bot.

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from the env chain.
Silent no-op if credentials are missing (so scrapers still work without them).
"""

from __future__ import annotations

import requests

from . import config

_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send(text: str, parse_mode: str = "HTML") -> bool:
    token = config.get("TELEGRAM_BOT_TOKEN")
    chat_id = config.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        resp = requests.post(
            _SEND_URL.format(token=token),
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        return resp.ok
    except Exception:
        return False


def alert(subject: str, detail: str = "") -> None:
    """Send a failure alert."""
    msg = f"🚨 <b>trending-scraper</b>: {subject}"
    if detail:
        msg += f"\n<pre>{detail[:800]}</pre>"
    send(msg)


def summary(counts: dict[str, int]) -> None:
    """Send a daily scrape summary."""
    lines = "\n".join(f"  {plat}: {n}" for plat, n in sorted(counts.items()))
    send(f"✅ <b>trending-scraper</b> daily scrape done\n<pre>{lines}</pre>")
