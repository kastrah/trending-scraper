"""Hacker News via the official Firebase API — free, no auth."""

from __future__ import annotations

from datetime import datetime, timezone

from ..fetchers import fetch
from ..items import Item

API = "https://hacker-news.firebaseio.com/v0"


def trending(listing: str = "top", limit: int = 30) -> list[Item]:
    ids = fetch(f"{API}/{listing}stories.json").json()[:limit]
    items = []
    for sid in ids:
        d = fetch(f"{API}/item/{sid}.json").json()
        if not d or d.get("dead") or d.get("deleted"):
            continue
        items.append(
            Item(
                platform="hackernews",
                id=str(d["id"]),
                url=d.get("url") or f"https://news.ycombinator.com/item?id={d['id']}",
                title=d.get("title", ""),
                text=d.get("text", "")[:2000],
                author=d.get("by", ""),
                created_at=datetime.fromtimestamp(
                    d.get("time", 0), tz=timezone.utc
                ).isoformat(timespec="seconds"),
                likes=d.get("score", 0),
                comments=d.get("descendants", 0),
                extra={"hn_url": f"https://news.ycombinator.com/item?id={d['id']}"},
            )
        )
    return items
