"""YouTube scraper — two tiers:

Tier 1 (API, preferred): YouTube Data API v3.
  Set YOUTUBE_API_KEY in .env. Free quota: 10,000 units/day.
  Get a key: console.cloud.google.com → APIs → YouTube Data API v3 → Credentials.
  Cost per call: videos.list=1 unit, search.list=100 units.

Tier 2 (no-auth fallback): scrape the YouTube trending page HTML.
  Returns fewer fields (no view counts) but requires no key.
  Covers worldwide trending; regionCode filtering only works with the API.
"""

from __future__ import annotations

import re
import json
from datetime import datetime, timezone

from .. import config
from ..fetchers import fetch  # used by _via_api
from ..items import Item

# YouTube category IDs relevant to health/pharma content
HEALTH_CATEGORY_ID = "26"   # "Howto & Style" — closest to health on YT
NEWS_CATEGORY_ID   = "25"   # News & Politics

# Region codes
REGIONS = {
    "nigeria":        "NG",
    "worldwide":      "US",   # YT doesn't have a true worldwide; US is the default
    "united-states":  "US",
    "united-kingdom": "GB",
    "ghana":          "GH",
    "kenya":          "KE",
    "south-africa":   "ZA",
}


def _parse_duration(iso: str) -> int:
    """PT4M13S → 253 seconds."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mn, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mn * 60 + s


def _via_api(region: str = "NG", category_id: str = "", limit: int = 50) -> list[Item]:
    api_key = config.get("YOUTUBE_API_KEY")
    params: dict = {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular",
        "regionCode": region,
        "maxResults": min(limit, 50),
        "key": api_key,
    }
    if category_id:
        params["videoCategoryId"] = category_id

    data = fetch("https://www.googleapis.com/youtube/v3/videos", params=params).json()

    items = []
    for v in data.get("items", []):
        snip = v.get("snippet", {})
        stats = v.get("statistics", {})
        details = v.get("contentDetails", {})
        vid_id = v.get("id", "")
        published = snip.get("publishedAt", "")
        items.append(
            Item(
                platform="youtube",
                id=vid_id,
                url=f"https://www.youtube.com/watch?v={vid_id}",
                title=snip.get("title", ""),
                text=snip.get("description", "")[:500],
                author=snip.get("channelTitle", ""),
                created_at=published,
                views=int(stats.get("viewCount", 0)),
                likes=int(stats.get("likeCount", 0)),
                comments=int(stats.get("commentCount", 0)),
                extra={
                    "channel_id": snip.get("channelId", ""),
                    "category_id": snip.get("categoryId", ""),
                    "duration_sec": _parse_duration(details.get("duration", "")),
                    "region": region,
                    "thumbnail": (snip.get("thumbnails", {}).get("high") or {}).get("url", ""),
                },
            )
        )
    return items


def _via_ytdlp_search(query: str, limit: int = 50) -> list[Item]:
    """Fallback: yt-dlp ytsearch — no trending feed needed, works without auth.
    Install: brew install yt-dlp  or  pip install yt-dlp"""
    import shutil
    import subprocess

    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        print("yt-dlp not found — install with: brew install yt-dlp")
        return []

    # ytsearch{N}: fetches exactly N items. Scale timeout to the count.
    search_url = f"ytsearch{limit}:{query}"
    timeout = max(60, limit * 5)  # ~5s per item, min 60s
    cmd = [
        ytdlp,
        "--flat-playlist",
        "--dump-json",
        "--no-warnings",
        "--quiet",
        search_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if not result.stdout.strip():
        print(f"yt-dlp returned no output: {result.stderr[:200]}")
        return []

    items = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            v = json.loads(line)
        except json.JSONDecodeError:
            continue
        vid_id = v.get("id", "")
        if not vid_id:
            continue
        upload_date = v.get("upload_date", "")
        created_at = (
            f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}T00:00:00+00:00"
            if len(upload_date) == 8 else ""
        )
        items.append(
            Item(
                platform="youtube",
                id=vid_id,
                url=v.get("url") or f"https://www.youtube.com/watch?v={vid_id}",
                title=v.get("title", ""),
                text=(v.get("description") or "")[:500],
                author=v.get("channel") or v.get("uploader", ""),
                created_at=created_at,
                views=v.get("view_count") or 0,
                likes=v.get("like_count") or 0,
                comments=v.get("comment_count") or 0,
                extra={
                    "duration_sec": v.get("duration") or 0,
                    "channel_id": v.get("channel_id", ""),
                    "thumbnail": v.get("thumbnail", ""),
                    "query": query,
                    "source": "ytdlp",
                },
            )
        )
    return items


# Default search queries per region (used when no API key is set)
REGION_QUERIES = {
    "NG": "trending nigeria",
    "GH": "trending ghana",
    "KE": "trending kenya",
    "ZA": "trending south africa",
    "GB": "trending uk",
    "US": "trending united states",
}

HEALTH_QUERIES = {
    "NG": "health nigeria 2026",
    "default": "health wellness trending",
}


def trending(region: str = "nigeria", category_id: str = "", limit: int = 50) -> list[Item]:
    region_code = REGIONS.get(region.lower(), region.upper())
    if config.get("YOUTUBE_API_KEY"):
        return _via_api(region_code, category_id, limit)
    query = REGION_QUERIES.get(region_code, f"trending {region}")
    print(f"note: YOUTUBE_API_KEY not set — searching yt-dlp: '{query}'")
    return _via_ytdlp_search(query, limit)


def health(region: str = "nigeria", limit: int = 50) -> list[Item]:
    """Health-focused videos for a region. Uses category filter with API key,
    or a targeted search query without one."""
    region_code = REGIONS.get(region.lower(), region.upper())
    if config.get("YOUTUBE_API_KEY"):
        return _via_api(region_code, HEALTH_CATEGORY_ID, limit)
    query = HEALTH_QUERIES.get(region_code, HEALTH_QUERIES["default"])
    print(f"note: YOUTUBE_API_KEY not set — searching yt-dlp: '{query}'")
    return _via_ytdlp_search(query, limit)
