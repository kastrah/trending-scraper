"""SQLite-backed storage with (platform, id) deduplication.

One database file per day: output/trending_YYYY-MM-DD.db
Each run upserts rows — re-running the same scraper never creates duplicates.

Legacy JSONL files (if any) are left untouched in output/.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import PROJECT_ROOT
from .items import Item

OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    platform    TEXT NOT NULL,
    id          TEXT NOT NULL,
    url         TEXT NOT NULL DEFAULT '',
    title       TEXT NOT NULL DEFAULT '',
    text        TEXT NOT NULL DEFAULT '',
    author      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT '',
    scraped_at  TEXT NOT NULL DEFAULT '',
    views       INTEGER NOT NULL DEFAULT 0,
    likes       INTEGER NOT NULL DEFAULT 0,
    comments    INTEGER NOT NULL DEFAULT 0,
    shares      INTEGER NOT NULL DEFAULT 0,
    extra       TEXT NOT NULL DEFAULT '{}',
    engagement  INTEGER NOT NULL DEFAULT 0,
    pct_score   REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (platform, id)
);
CREATE INDEX IF NOT EXISTS idx_engagement ON items (engagement DESC);
CREATE INDEX IF NOT EXISTS idx_platform   ON items (platform, engagement DESC);
CREATE INDEX IF NOT EXISTS idx_scraped    ON items (scraped_at DESC);
"""


def _db_path(day: str | None = None) -> Path:
    if day is None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return OUTPUT_DIR / f"trending_{day}.db"


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def write_items(items: Iterable[Item], platform: str, label: str = "") -> Path:
    """Upsert items into today's database. Returns the db path."""
    path = _db_path()
    conn = _connect(path)
    rows = list(items)
    with conn:
        conn.executemany(
            """
            INSERT INTO items
              (platform, id, url, title, text, author, created_at, scraped_at,
               views, likes, comments, shares, extra, engagement)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(platform, id) DO UPDATE SET
              scraped_at  = excluded.scraped_at,
              views       = MAX(views,    excluded.views),
              likes       = MAX(likes,    excluded.likes),
              comments    = MAX(comments, excluded.comments),
              shares      = MAX(shares,   excluded.shares),
              engagement  = excluded.engagement
            """,
            [
                (
                    r.platform, r.id, r.url, r.title, r.text, r.author,
                    r.created_at, r.scraped_at,
                    r.views, r.likes, r.comments, r.shares,
                    json.dumps(r.extra, ensure_ascii=False),
                    r.engagement,
                )
                for r in rows
            ],
        )
        # Recompute per-platform percentile scores after every write
        _update_percentiles(conn)

    n = len(rows)
    tag = f" [{label}]" if label else ""
    print(f"upserted {n} {platform}{tag} items → {path.name}")
    return path


def _update_percentiles(conn: sqlite3.Connection) -> None:
    """Assign a 0–100 percentile score within each platform's current rows."""
    platforms = [r[0] for r in conn.execute("SELECT DISTINCT platform FROM items")]
    for plat in platforms:
        rows = conn.execute(
            "SELECT id, engagement FROM items WHERE platform=? ORDER BY engagement",
            (plat,),
        ).fetchall()
        n = len(rows)
        if n == 0:
            continue
        updates = [
            (round(100 * i / (n - 1), 1) if n > 1 else 50.0, plat, row["id"])
            for i, row in enumerate(rows)
        ]
        conn.executemany(
            "UPDATE items SET pct_score=? WHERE platform=? AND id=?", updates
        )


def load_items(
    days: int = 1,
    platform: str = "",
    min_pct: float = 0.0,
    db_paths: list[Path] | None = None,
) -> list[dict]:
    """Load items from one or more day databases, deduped, sorted by engagement."""
    if db_paths is None:
        db_paths = sorted(OUTPUT_DIR.glob("trending_*.db"))[-days:]
    if not db_paths:
        return []

    seen: set[tuple[str, str]] = set()
    rows: list[dict] = []

    for path in db_paths:
        conn = _connect(path)
        query = "SELECT * FROM items WHERE pct_score >= ?"
        params: list = [min_pct]
        if platform:
            query += " AND platform = ?"
            params.append(platform)
        query += " ORDER BY engagement DESC"
        for row in conn.execute(query, params):
            key = (row["platform"], row["id"])
            if key in seen:
                continue
            seen.add(key)
            d = dict(row)
            d["extra"] = json.loads(d["extra"])
            rows.append(d)

    rows.sort(key=lambda r: r["engagement"], reverse=True)
    return rows
