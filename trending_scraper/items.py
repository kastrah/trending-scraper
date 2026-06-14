"""Normalized item schema — every scraper emits these, so ranking/reporting
doesn't care which platform an item came from (pattern borrowed from snscrape)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class Item:
    platform: str          # "reddit", "x", "tiktok", "telegram", "hackernews"
    id: str                # platform-native id
    url: str
    title: str = ""        # title/caption; falls back to first line of text
    text: str = ""
    author: str = ""
    created_at: str = ""   # ISO 8601 UTC
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    # Engagement — leave at 0 when the platform doesn't expose the metric
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    extra: dict = field(default_factory=dict)  # platform-specific leftovers

    @property
    def engagement(self) -> int:
        """Raw engagement count. Views dampened 100× so video platforms don't
        swamp text platforms. Per-platform percentile normalisation happens in
        storage._update_percentiles() after every write."""
        return self.likes + 2 * self.comments + 3 * self.shares + self.views // 100

    def to_json(self) -> str:
        d = asdict(self)
        d["engagement"] = self.engagement
        return json.dumps(d, ensure_ascii=False)
