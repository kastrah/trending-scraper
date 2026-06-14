"""TikTok scraper — two tiers:

Tier 1 (headless Playwright, works on VPS):
  TikTokApi with headless=True + msToken cookie. No display needed.
  Install: pip install TikTokApi && playwright install chromium

Tier 2 (headed, local only):
  Falls back to headless=False when TIKTOK_HEADED=1 is set (useful for
  debugging / re-auth).

The msToken cookie is extracted by scripts/extract_cookies.py and stored in
~/.hermes/.env as TIKTOK_MS_TOKEN. It expires after a few weeks — re-run
extract_cookies.py when scrapes start returning 0 results.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .. import config
from ..items import Item


def _to_item(video) -> Item:
    v = video.as_dict
    stats = v.get("stats", {})
    author = v.get("author", {})
    vid_id = str(v.get("id", ""))
    username = author.get("uniqueId", "")
    return Item(
        platform="tiktok",
        id=vid_id,
        url=f"https://www.tiktok.com/@{username}/video/{vid_id}",
        title=(v.get("desc") or "")[:120],
        text=v.get("desc", ""),
        author=username,
        created_at=datetime.fromtimestamp(
            v.get("createTime", 0), tz=timezone.utc
        ).isoformat(timespec="seconds"),
        views=stats.get("playCount", 0),
        likes=stats.get("diggCount", 0),
        comments=stats.get("commentCount", 0),
        shares=stats.get("shareCount", 0),
        extra={
            "hashtags": [t.get("hashtagName", "") for t in v.get("challenges", [])],
            "music": v.get("music", {}).get("title", ""),
            "duration_sec": v.get("video", {}).get("duration", 0),
            "author_followers": v.get("authorStats", {}).get("followerCount", 0),
        },
    )


async def _scrape(mode: str, query: str, count: int) -> list[Item]:
    from TikTokApi import TikTokApi

    ms_token = config.get("TIKTOK_MS_TOKEN")
    headed = config.get("TIKTOK_HEADED", "").lower() in ("1", "true", "yes")

    items: list[Item] = []
    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token] if ms_token else [],
            num_sessions=1,
            sleep_after=3,
            headless=not headed,   # headless by default — works on VPS
            browser="chromium",
        )
        if mode == "trending":
            gen = api.trending.videos(count=count)
        elif mode == "hashtag":
            gen = api.hashtag(name=query).videos(count=count)
        elif mode == "user":
            gen = api.user(username=query).videos(count=count)
        else:
            gen = api.search.videos(query, count=count)

        async for video in gen:
            items.append(_to_item(video))

    return items


def scrape(mode: str = "trending", query: str = "", count: int = 30) -> list[Item]:
    try:
        import TikTokApi as _  # noqa: F401
    except ImportError:
        print("TikTokApi not installed: pip install TikTokApi && playwright install chromium")
        return []
    if not config.get("TIKTOK_MS_TOKEN"):
        print("warning: TIKTOK_MS_TOKEN not set — TikTok may block requests")
        print("run: python scripts/extract_cookies.py")
    return asyncio.run(_scrape(mode, query, count))
