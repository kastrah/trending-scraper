"""Instagram via the internal web API — uses session cookie extracted by
extract_cookies.py (INSTAGRAM_SESSION_ID + INSTAGRAM_DS_USER_ID in .env).

Endpoints used (no official API key needed):
  - /api/v1/tags/{hashtag}/sections/   — hashtag top/recent posts
  - /api/v1/feed/reels/media/           — Reels feed (trending-ish)
  - graphql/query with explore_grid     — Explore page posts

Run scripts/extract_cookies.py to get session cookies from your logged-in
Chrome profile, then these endpoints work without any developer account.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .. import config
from ..fetchers import fetch
from ..items import Item

APP_ID = "936619743392459"  # Instagram web app ID (public)


def _session_headers() -> dict:
    session_id = config.get("INSTAGRAM_SESSION_ID")
    ds_user_id = config.get("INSTAGRAM_DS_USER_ID")
    csrf = config.get("INSTAGRAM_CSRF_TOKEN")
    if not session_id:
        raise RuntimeError(
            "INSTAGRAM_SESSION_ID not set — run scripts/extract_cookies.py "
            "after logging into Instagram in the Chrome debug profile"
        )
    cookie = f"sessionid={session_id}"
    if ds_user_id:
        cookie += f"; ds_user_id={ds_user_id}"
    if csrf:
        cookie += f"; csrftoken={csrf}"
    headers = {
        "Cookie": cookie,
        "X-IG-App-ID": APP_ID,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/",
    }
    if csrf:
        headers["X-CSRFToken"] = csrf
    return headers


def _ts(epoch: int | None) -> str:
    if not epoch:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="seconds")


def hashtag(tag: str, limit: int = 30) -> list[Item]:
    """Fetch top posts for a hashtag."""
    tag = tag.lstrip("#")
    try:
        headers = _session_headers()
    except RuntimeError as e:
        print(f"instagram: {e}")
        return []
    url = f"https://www.instagram.com/api/v1/tags/{tag}/sections/"
    data = fetch(
        url,
        method="POST",
        headers=headers,
        data={"tab": "top", "count": min(limit, 30), "page": 1},
    ).json()

    items = []
    for section in data.get("sections", []):
        for layout_item in section.get("layout_content", {}).get("medias", []):
            m = layout_item.get("media", {})
            caption = (m.get("caption") or {}).get("text", "")
            user = (m.get("user") or {}).get("username", "")
            shortcode = m.get("code", "")
            items.append(
                Item(
                    platform="instagram",
                    id=str(m.get("pk", shortcode)),
                    url=f"https://www.instagram.com/p/{shortcode}/",
                    title=caption[:120],
                    text=caption[:2000],
                    author=user,
                    created_at=_ts(m.get("taken_at")),
                    likes=m.get("like_count", 0),
                    comments=m.get("comment_count", 0),
                    views=m.get("play_count", 0) or m.get("view_count", 0),
                    extra={
                        "media_type": m.get("media_type"),  # 1=photo, 2=video, 8=carousel
                        "hashtag": tag,
                    },
                )
            )
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    return items


def user_feed(username: str) -> list[Item]:
    """Fetch a user's recent posts."""
    try:
        headers = _session_headers()
    except RuntimeError as e:
        print(f"instagram: {e}")
        return []
    # Resolve user ID first
    info = fetch(
        f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
        headers=headers,
    ).json()
    user_data = info.get("data", {}).get("user", {})
    user_id = user_data.get("id")
    if not user_id:
        raise RuntimeError(f"Could not resolve Instagram user: {username}")

    url = f"https://www.instagram.com/api/v1/feed/user/{user_id}/"
    data = fetch(url, headers=headers).json()

    items = []
    for m in data.get("items", []):
        caption = (m.get("caption") or {}).get("text", "")
        shortcode = m.get("code", "")
        items.append(
            Item(
                platform="instagram",
                id=str(m.get("pk", shortcode)),
                url=f"https://www.instagram.com/p/{shortcode}/",
                title=caption[:120],
                text=caption[:2000],
                author=username,
                created_at=_ts(m.get("taken_at")),
                likes=m.get("like_count", 0),
                comments=m.get("comment_count", 0),
                views=m.get("play_count", 0),
                extra={"media_type": m.get("media_type")},
            )
        )
    return items
