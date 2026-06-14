"""X/Twitter, no official API needed.

  user_timeline()  — syndication.twitter.com: server-rendered timeline JSON
                     embedded in HTML. Free, no auth, recent ~20 posts per user.
  post_via_bd()    — Bright Data fetch + OG-tag parsing for individual posts.
                     Only call when use_brightdata=True.
  trends()         — trends24.in (server-rendered trend aggregator).

Background: vxtwitter and fxtwitter stopped working in mid-2026 due to
Twitter API changes. The syndication API still works for reading user timelines.
"""

from __future__ import annotations

import json
import re
from html import unescape

import requests

from ..fetchers import fetch, fetch_brightdata
from ..items import Item

POST_URL_RE = re.compile(r"(?:x|twitter)\.com/([^/]+)/status/(\d+)")
TAG_RE = re.compile(r"<[^>]+>")
NEXT_DATA_RE = re.compile(r'id="__NEXT_DATA__"[^>]*>({.*?})</script>', re.DOTALL)


def _parse_og(html: str, tweet_id: str, user: str) -> Item:
    """Build an Item from OG meta tags in a Bright Data HTML response."""

    def og(prop: str) -> str:
        m = re.search(rf'<meta[^>]+property="og:{prop}"[^>]+content="([^"]*)"', html)
        return unescape(m.group(1)) if m else ""

    text = og("description")
    title = og("title")  # typically "Name on X: ..."
    return Item(
        platform="x",
        id=tweet_id,
        url=f"https://x.com/{user}/status/{tweet_id}",
        title=text[:120],
        text=text,
        author=user,
        extra={"og_title": title, "source": "brightdata"},
    )


def post_via_bd(url_or_id: str, username: str = "i") -> Item:
    m = POST_URL_RE.search(url_or_id)
    user, tweet_id = (m.group(1), m.group(2)) if m else (username, url_or_id)
    html = fetch_brightdata(f"https://x.com/{user}/status/{tweet_id}")
    return _parse_og(html, tweet_id, user)


def user_timeline(username: str) -> list[Item]:
    """Fetch a user's recent public tweets via the syndication API.
    Returns up to ~20 posts (what the API embeds per page load).
    """
    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
    html = fetch(url).text
    m = NEXT_DATA_RE.search(html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []

    entries = (
        data.get("props", {})
        .get("pageProps", {})
        .get("timeline", {})
        .get("entries", [])
    )
    items = []
    for entry in entries:
        t = entry.get("content", {}).get("tweet", {})
        if not t:
            continue
        tid = str(t.get("id_str", ""))
        text = t.get("full_text", "")
        items.append(
            Item(
                platform="x",
                id=tid,
                url=f"https://x.com/{username}/status/{tid}",
                title=text[:120],
                text=text,
                author=username,
                created_at=t.get("created_at", ""),
                likes=t.get("favorite_count", 0),
                comments=t.get("reply_count", 0),
                shares=t.get("retweet_count", 0),
                extra={
                    "quote_count": t.get("quote_count", 0),
                    "lang": t.get("lang", ""),
                    "source": "syndication",
                },
            )
        )
    return items


def posts(urls_or_ids: list[str], use_brightdata: bool = False) -> list[Item]:
    """Hydrate a list of post URLs or IDs.

    Without Bright Data: groups by username and fetches each user's syndication
    timeline, then filters to just the requested tweet IDs (only works if the
    tweet is in their recent ~20).

    With --brightdata: fetches each URL individually through Bright Data and
    parses OG tags (slower but reliable for any public tweet).
    """
    if use_brightdata:
        items = []
        for u in urls_or_ids:
            try:
                items.append(post_via_bd(u))
            except Exception as e:
                print(f"  skip {u}: {e}")
        return items

    # Group requested IDs by username for syndication lookups
    by_user: dict[str, list[str]] = {}
    for u in urls_or_ids:
        m = POST_URL_RE.search(u)
        if m:
            by_user.setdefault(m.group(1), []).append(m.group(2))
        else:
            print(f"  skip {u}: can't parse username from URL (pass full x.com URL)")

    items = []
    for username, ids in by_user.items():
        try:
            timeline = user_timeline(username)
        except Exception as e:
            print(f"  skip @{username} timeline: {e}")
            continue
        id_set = set(ids)
        found = [item for item in timeline if item.id in id_set]
        missing = id_set - {item.id for item in found}
        items.extend(found)
        for mid in missing:
            print(f"  note: {username}/{mid} not in recent syndication timeline — use --brightdata")
    return items


TREND_RE = re.compile(r'<a[^>]*href="[^"]*(?:twitter|x)\.com/search[^"]*"[^>]*>([^<]+)</a>')


def trends(region: str = "", use_brightdata: bool = False) -> list[Item]:
    url = f"https://trends24.in/{region}" if region else "https://trends24.in/"
    html = fetch_brightdata(url) if use_brightdata else fetch(url).text

    seen: set[str] = set()
    items = []
    for rank, m in enumerate(TREND_RE.finditer(html), 1):
        name = unescape(m.group(1)).strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        items.append(
            Item(
                platform="x",
                id=f"trend:{region or 'worldwide'}:{name}",
                url="https://x.com/search?q=" + requests.utils.quote(name),
                title=name,
                extra={"kind": "trend", "region": region or "worldwide", "rank": rank},
            )
        )
        if len(items) >= 50:
            break
    return items
