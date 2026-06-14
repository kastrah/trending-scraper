"""Reddit via public JSON endpoints.

Auth tiers (tried in order):
  1. Session cookie (REDDIT_TOKEN_V2 from .env — extracted via extract_cookies.py)
  2. OAuth client credentials (REDDIT_CLIENT_ID + REDDIT_SECRET)
  3. Bright Data Web Unlocker (--brightdata flag)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .. import config
from ..fetchers import fetch, fetch_brightdata
from ..items import Item


def _get_oauth_token() -> str | None:
    client_id = config.get("REDDIT_CLIENT_ID")
    secret = config.get("REDDIT_SECRET")
    if not client_id or not secret:
        return None
    resp = fetch(
        "https://www.reddit.com/api/v1/access_token",
        method="POST",
        auth=(client_id, secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": "script:trending-scraper:v0.1"},
    )
    return resp.json().get("access_token")


def trending(
    subreddit: str = "all",
    listing: str = "hot",
    limit: int = 50,
    use_brightdata: bool = False,
) -> list[Item]:
    url = f"https://www.reddit.com/r/{subreddit}/{listing}.json?limit={min(limit, 100)}"

    if use_brightdata:
        raw = fetch_brightdata(url)
        # Bright Data returns the page HTML; Reddit embeds JSON in a <script> or
        # responds with pure JSON depending on how the request is routed.
        # Try raw JSON first, fall back to extracting from HTML.
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r'window\.__r = ({.*?});</script>', raw, re.DOTALL)
            if not m:
                raise RuntimeError("Could not parse Reddit response from Bright Data")
            data = json.loads(m.group(1))
    else:
        headers = {"User-Agent": "script:trending-scraper:v0.1"}
        # Tier 1: token_v2 is Reddit's OAuth JWT stored as a browser cookie —
        # use it as a Bearer token against oauth.reddit.com (bypasses Cloudflare)
        token_v2 = config.get("REDDIT_TOKEN_V2")
        if token_v2:
            headers["Authorization"] = f"Bearer {token_v2}"
            url = url.replace("www.reddit.com", "oauth.reddit.com")
        else:
            # Tier 2: OAuth client credentials (REDDIT_CLIENT_ID + REDDIT_SECRET)
            token = _get_oauth_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
                url = url.replace("www.reddit.com", "oauth.reddit.com")
        resp = fetch(url, headers=headers)
        data = resp.json()

    items = []
    for child in data["data"]["children"]:
        d = child["data"]
        items.append(
            Item(
                platform="reddit",
                id=d["id"],
                url="https://www.reddit.com" + d["permalink"],
                title=d.get("title", ""),
                text=d.get("selftext", "")[:2000],
                author=d.get("author", ""),
                created_at=datetime.fromtimestamp(
                    d.get("created_utc", 0), tz=timezone.utc
                ).isoformat(timespec="seconds"),
                likes=d.get("ups", 0),
                comments=d.get("num_comments", 0),
                extra={
                    "subreddit": d.get("subreddit", ""),
                    "upvote_ratio": d.get("upvote_ratio"),
                    "flair": d.get("link_flair_text"),
                    "is_video": d.get("is_video", False),
                    "external_url": d.get("url_overridden_by_dest", ""),
                },
            )
        )
    return items
