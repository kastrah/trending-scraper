"""CLI entry point.

  python -m trending_scraper doctor                                              check credentials + tools
  python -m trending_scraper reddit     [--subreddit all] [--listing hot] [--count 50] [--brightdata]
  python -m trending_scraper hn         [--listing top] [--count 30]
  python -m trending_scraper telegram   --channel <name> [--brightdata]
  python -m trending_scraper xtrends    [--region united-states] [--brightdata]
  python -m trending_scraper xuser      --username <handle> [<handle> ...]
  python -m trending_scraper xposts     --urls <url> [<url> ...] [--brightdata]
  python -m trending_scraper instagram  --hashtag <tag> | --user <username> [--count 30]
  python -m trending_scraper youtube    [--region nigeria] [--health] [--count 50]
  python -m trending_scraper tiktok     [--mode trending|hashtag|user|search] [--query q] [--count 30]
  python -m trending_scraper report     [--top 25] [--platform x] [--keyword term] [--days 7] [--min-pct 50]
  python -m trending_scraper readurl    <url> [--brightdata] [--limit 5000]      extract article text
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .storage import OUTPUT_DIR, load_items, write_items


def cmd_report(args) -> None:
    rows = load_items(
        days=args.days,
        platform=args.platform,
        min_pct=args.min_pct,
    )
    if not rows:
        sys.exit("no items found — run a scraper first")
    if args.keyword:
        kw = args.keyword.lower()
        rows = [
            r for r in rows
            if kw in (r.get("title") or "").lower() or kw in (r.get("text") or "").lower()
        ]
        if not rows:
            sys.exit(f"no items matched keyword '{args.keyword}'")
    for r in rows[: args.top]:
        title = (r.get("title") or r.get("text") or "")[:80].replace("\n", " ")
        pct = r.get("pct_score", 0)
        print(f"{r.get('engagement', 0):>9,}  pct={pct:>5.1f}  [{r['platform']:>10}]  {title}")
        print(f"{'':>9}              {r['url']}")


def cmd_readurl(args) -> None:
    from .fetchers import fetch_brightdata, fetch_jina
    if args.brightdata:
        content = fetch_brightdata(args.url)
        print(f"[Bright Data · {len(content):,} chars]\n")
    else:
        content = fetch_jina(args.url)
        print(f"[Jina Reader · {len(content):,} chars]\n")
    limit = args.limit or len(content)
    print(content[:limit])
    if args.limit and len(content) > args.limit:
        print(f"\n[truncated — full response is {len(content):,} chars]")


def main() -> None:
    parser = argparse.ArgumentParser(prog="trending_scraper")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check credentials and tool availability for all platforms")

    p = sub.add_parser("reddit", help="hot/top posts from a subreddit (default r/all)")
    p.add_argument("--subreddit", default="all")
    p.add_argument("--listing", default="hot", choices=["hot", "top", "rising", "new"])
    p.add_argument("--count", type=int, default=50)
    p.add_argument("--brightdata", action="store_true", help="fetch via Bright Data (bypasses Cloudflare)")

    p = sub.add_parser("hn", help="Hacker News front page")
    p.add_argument("--listing", default="top", choices=["top", "best", "new"])
    p.add_argument("--count", type=int, default=30)

    p = sub.add_parser("telegram", help="recent posts from a public channel")
    p.add_argument("--channel", required=True)
    p.add_argument("--brightdata", action="store_true", help="fetch via Bright Data")

    p = sub.add_parser("xtrends", help="X trending topics via trends24.in")
    p.add_argument("--region", default="", help="e.g. united-states, nigeria")
    p.add_argument("--brightdata", action="store_true")

    p = sub.add_parser("xuser", help="recent posts from X user(s) via syndication API")
    p.add_argument("--username", nargs="+", required=True, help="one or more @handles")

    p = sub.add_parser("xposts", help="hydrate specific X posts by URL")
    p.add_argument("--urls", nargs="+", required=True, metavar="URL")
    p.add_argument("--brightdata", action="store_true",
                   help="fetch via Bright Data (required if tweet is not in recent timeline)")

    p = sub.add_parser("instagram", help="Instagram hashtag/user posts (needs session cookie)")
    p.add_argument("--hashtag", default="", help="hashtag to scrape (without #)")
    p.add_argument("--user", default="", help="username to scrape")
    p.add_argument("--count", type=int, default=30)

    p = sub.add_parser("youtube", help="YouTube trending videos (API key optional)")
    p.add_argument("--region", default="nigeria", help="e.g. nigeria, united-states, ghana")
    p.add_argument("--health", action="store_true", help="filter to health/howto category")
    p.add_argument("--count", type=int, default=50)

    p = sub.add_parser("tiktok", help="TikTok via TikTokApi (headless, needs Playwright)")
    p.add_argument("--mode", default="trending", choices=["trending", "hashtag", "user", "search"])
    p.add_argument("--query", default="")
    p.add_argument("--count", type=int, default=30)

    p = sub.add_parser("report", help="rank collected items by engagement")
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--platform", default="", help="filter to one platform")
    p.add_argument("--days", type=int, default=1, help="how many daily DBs to include")
    p.add_argument("--min-pct", type=float, default=0.0, dest="min_pct",
                   help="only show items above this platform percentile (0-100)")
    p.add_argument("--keyword", default="", help="filter title+text to items containing this word")

    p = sub.add_parser("readurl", help="extract clean text from any URL (via Jina Reader)")
    p.add_argument("url", help="URL to fetch")
    p.add_argument("--brightdata", action="store_true", help="use Bright Data instead of Jina")
    p.add_argument("--limit", type=int, default=0, help="truncate output to N chars (0 = no limit)")

    args = parser.parse_args()

    if args.command == "doctor":
        from .doctor import run_doctor
        sys.exit(0 if run_doctor() else 1)
    elif args.command == "reddit":
        from .scrapers import reddit
        write_items(
            reddit.trending(args.subreddit, args.listing, args.count, args.brightdata),
            "reddit", args.subreddit,
        )
    elif args.command == "hn":
        from .scrapers import hackernews
        write_items(hackernews.trending(args.listing, args.count), "hackernews")
    elif args.command == "telegram":
        from .scrapers import telegram
        write_items(telegram.channel(args.channel, args.brightdata),
                    "telegram", args.channel)
    elif args.command == "xtrends":
        from .scrapers import x
        write_items(x.trends(args.region, args.brightdata),
                    "x", f"trends_{args.region or 'worldwide'}")
    elif args.command == "xuser":
        from .scrapers import x
        items = []
        for handle in args.username:
            items.extend(x.user_timeline(handle.lstrip("@")))
        write_items(items, "x", "users")
    elif args.command == "xposts":
        from .scrapers import x
        write_items(x.posts(args.urls, args.brightdata), "x", "posts")
    elif args.command == "instagram":
        from .scrapers import instagram
        if args.hashtag:
            write_items(instagram.hashtag(args.hashtag, args.count), "instagram", args.hashtag)
        elif args.user:
            write_items(instagram.user_feed(args.user), "instagram", args.user)
        else:
            sys.exit("instagram: pass --hashtag or --user")
    elif args.command == "youtube":
        from .scrapers import youtube
        if args.health:
            write_items(youtube.health(region=args.region, limit=args.count), "youtube", f"{args.region}_health")
        else:
            write_items(youtube.trending(region=args.region, limit=args.count), "youtube", args.region)
    elif args.command == "tiktok":
        from .scrapers import tiktok
        write_items(tiktok.scrape(args.mode, args.query, args.count),
                    "tiktok", args.query or args.mode)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "readurl":
        cmd_readurl(args)


if __name__ == "__main__":
    main()
