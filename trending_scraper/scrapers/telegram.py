"""Telegram public channels via the t.me/s/<channel> web preview.

Server-rendered HTML, no auth. If Telegram starts blocking the plain request,
the same URL works through fetch_brightdata()."""

from __future__ import annotations

import re

from ..fetchers import fetch, fetch_brightdata
from ..items import Item

MSG_RE = re.compile(
    r'data-post="(?P<post>[^"]+)".*?'
    r'(?:tgme_widget_message_text[^>]*>(?P<text>.*?)</div>)?.*?'
    r'datetime="(?P<dt>[^"]+)"',
    re.DOTALL,
)
VIEWS_RE = re.compile(r'tgme_widget_message_views[^>]*>([^<]+)<')
TAG_RE = re.compile(r"<[^>]+>")


def _parse_views(s: str) -> int:
    s = s.strip().upper()
    mult = 1
    if s.endswith("K"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("M"):
        mult, s = 1_000_000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0


def channel(name: str, use_brightdata: bool = False) -> list[Item]:
    url = f"https://t.me/s/{name}"
    html = fetch_brightdata(url) if use_brightdata else fetch(url).text

    items = []
    # Each message sits in its own tgme_widget_message block
    blocks = html.split('tgme_widget_message_wrap')[1:]
    for block in blocks:
        post = re.search(r'data-post="([^"]+)"', block)
        if not post:
            continue
        text_m = re.search(
            r'tgme_widget_message_text[^>]*>(.*?)</div>', block, re.DOTALL
        )
        text = TAG_RE.sub(" ", text_m.group(1)).strip() if text_m else ""
        dt_m = re.search(r'datetime="([^"]+)"', block)
        views_m = VIEWS_RE.search(block)
        items.append(
            Item(
                platform="telegram",
                id=post.group(1),
                url=f"https://t.me/{post.group(1)}",
                title=text[:120],
                text=text[:2000],
                author=name,
                created_at=dt_m.group(1) if dt_m else "",
                views=_parse_views(views_m.group(1)) if views_m else 0,
            )
        )
    return items
