# trending-scraper

Multi-platform trending content scraper for social and online media intelligence.

Collects trending posts from Reddit, X/Twitter, Instagram, YouTube, TikTok, Telegram public channels, and Hacker News. Normalises everything into a single schema, deduplicates across runs, scores by engagement percentile per platform, and surfaces a unified ranked view of what's trending — across all platforms at once.

Built to run unattended on a Linux VPS (cron + Telegram alerts) while cookie extraction stays on a local Mac using a persistent Chrome profile.

---

## Architecture

```
 Platforms                  Scrapers                Storage & Scoring
 ─────────────────────      ────────────────────     ─────────────────────────
 Reddit oauth API    ──▶    scrapers/reddit.py  ─┐
 X syndication API   ──▶    scrapers/x.py       ─┤
 Instagram web API   ──▶    scrapers/instagram.py─┤   SQLite (daily DB)
 YouTube Data API    ──▶    scrapers/youtube.py  ─┼──▶ trending_YYYY-MM-DD.db
 TikTok (Playwright) ──▶    scrapers/tiktok.py   ─┤   • upsert on (platform, id)
 Telegram t.me/s/   ──▶    scrapers/telegram.py ─┤   • max-engagement upsert
 HN Firebase API    ──▶    scrapers/hackernews.py─┘   • per-platform pct_score
          │
          │  (bot-walled pages)
          ▼
 Bright Data Web Unlocker
 (proxy fallback)
```

Every scraper returns a list of `Item` objects with a common schema:

```
Item
 ├── platform      reddit | x | instagram | youtube | tiktok | telegram | hackernews
 ├── id            platform-native post/video/tweet ID
 ├── url           canonical link
 ├── title / text  post content
 ├── author
 ├── created_at    ISO 8601
 ├── views / likes / comments / shares
 ├── engagement    likes + 2×comments + 3×shares + views÷100
 └── pct_score     0–100 percentile within the platform (recalculated after each write)
```

The engagement formula weights comments and shares higher than likes (stronger signals) and scales down views (video platforms report orders of magnitude more).

---

## Platforms

| Platform | Auth method | What it collects |
|---|---|---|
| **Reddit** | Browser cookie (`token_v2`) → OAuth creds → Bright Data | Subreddit hot/top/rising posts with score and comment counts |
| **X / Twitter** | Syndication API (no auth) for timelines; trends24.in for trends | User timelines (~20 recent posts/user), regional trending topics |
| **Instagram** | Session cookie (`sessionid` + `csrftoken`) | Hashtag top posts, user feed posts |
| **YouTube** | YouTube Data API v3 → yt-dlp search fallback | Most-popular videos by region and category; works without an API key |
| **TikTok** | Playwright headless + `msToken` cookie via [TikTok-Api](https://github.com/davidteather/TikTok-Api) | Trending feed, hashtag, user, or keyword search |
| **Telegram** | Public channel web preview — no auth | Posts from public broadcast channels (`t.me/s/{channel}`) |
| **Hacker News** | Firebase REST API — no auth | Front-page top/best/new stories with score and comment counts |

---

## How it works

### Authentication tiers

Each platform tries multiple backends in order, degrading gracefully rather than crashing:

```
Reddit:    token_v2 cookie (Bearer) → OAuth client creds → Bright Data proxy
YouTube:   YouTube Data API v3      → yt-dlp search (no key, no quota)
X trends:  direct fetch (trends24.in) → Bright Data proxy
Instagram: sessionid cookie (required — returns [] with warning if missing)
TikTok:    Playwright + msToken     (returns [] with warning if Playwright not installed)
HN:        Firebase API             (always free, no auth)
Telegram:  direct fetch             (public channels only)
```

### Cookie extraction

`scripts/extract_cookies.py` connects to a running Chrome instance on port 9222 via the Chrome DevTools Protocol (CDP). It reads cookies from your existing browser session — no need to log in again or paste tokens manually — and writes them to `~/.hermes/.env`.

A launchd job (`scripts/refresh_cookies.sh --install`) re-runs extraction every 6 hours so cookies stay fresh without manual intervention.

### Deduplication and scoring

Each platform writes to `output/trending_YYYY-MM-DD.db` using `(platform, id)` as the primary key. Re-runs upsert with `MAX(engagement)` so numbers only ever go up. After every write, `pct_score` is recalculated across all items per platform, giving a 0–100 percentile rank within each platform's pool. This makes cross-platform comparison meaningful: a Reddit post at `pct_score=90` is performing as well relative to Reddit as a YouTube video at `pct_score=90` is relative to YouTube.

### Bright Data proxy

For pages that actively block scrapers, the `--brightdata` flag routes requests through the Bright Data Web Unlocker REST API. Returns server-rendered HTML only (no JS execution). Used selectively — most platforms work without it.

### Article extraction (Jina Reader)

```bash
python -m trending_scraper readurl "https://example.com/article"
```

Fetches any URL via [Jina Reader](https://jina.ai/reader/) and returns clean markdown. Useful for reading the full text of articles linked in trending posts without opening a browser. Free, no API key needed.

---

## Deployment

```
┌────────────────────────────────┐           ┌────────────────────────────────┐
│          Mac (local)           │           │           VPS (Linux)           │
│                                │           │                                │
│  Chrome  ──▶  port 9222 (CDP)  │           │  cron @ 05:00 UTC daily        │
│                   │            │           │    reddit / x / instagram /     │
│          extract_cookies.py    │──rsync──▶ │    youtube / tiktok / hn /     │
│          (launchd, every 6h)   │  +SSH     │    telegram                    │
│                   │            │           │         │                      │
│          ~/.hermes/.env        │           │  output/trending_YYYY-MM-DD.db │
│          (session cookies)     │           │         │                      │
│                                │           │  Telegram bot alerts           │
│  python -m trending_scraper    │           │  • failures notified instantly  │
│    report / readurl            │           │  • daily summary on completion  │
│                                │           │                                │
└────────────────────────────────┘           └────────────────────────────────┘
```

---

## Setup

### Prerequisites

- Python 3.10+
- Google Chrome (for cookie extraction on Mac)
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) — YouTube fallback: `brew install yt-dlp` or `pip install yt-dlp`
- [TikTok-Api](https://github.com/davidteather/TikTok-Api) + Playwright + Chromium — TikTok only: `pip install TikTokApi && playwright install chromium`

### Install

```bash
git clone https://github.com/kastrah/trending-scraper.git
cd trending-scraper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure credentials

Copy `.env.example` to `.env` and uncomment the values you have, **or** let `extract_cookies.py` fill them in automatically:

```bash
# 1. Start Chrome using the persistent debug profile (first time only)
bash scripts/launch_chrome_debug.sh

# 2. Log into each platform you want to scrape in that Chrome window
#    (reddit.com, instagram.com, tiktok.com, x.com)

# 3. Extract all cookies into ~/.hermes/.env
python scripts/extract_cookies.py
```

For Reddit and YouTube, the scraper also works without API keys — it falls back to the browser cookie and yt-dlp search respectively.

### Health check

Before running, verify everything is configured:

```bash
python -m trending_scraper doctor
```

Example output:

```
trending-scraper health check

  ✓ [ok  ]  hackernews    free Firebase API — no auth needed
  ✓ [ok  ]  reddit        REDDIT_TOKEN_V2 set (browser cookie, tier 1)
  ✓ [ok  ]  x             syndication API (no auth) for timelines; Bright Data for trends
  ✓ [ok  ]  instagram     session + CSRF token set
  ~ [warn]  youtube       no API key — yt-dlp search fallback (2026.03.17)
  ✓ [ok  ]  tiktok        Playwright ok + ms_token set
  ✓ [ok  ]  telegram      public channel scraping ok + bot alerts configured
  ✓ [ok  ]  brightdata    API key set (zone: web_unlocker1)

All checks passed (warnings are non-fatal).
```

`warn` means a non-critical fallback is in use. `ERR` means that platform will fail — fix it before running cron.

---

## Usage

```bash
# ── Scrape platforms ───────────────────────────────────────────────────────────
python -m trending_scraper hn
python -m trending_scraper reddit --subreddit all --count 50
python -m trending_scraper reddit --subreddit Nigeria --listing hot --count 30
python -m trending_scraper xtrends --region nigeria
python -m trending_scraper xtrends --region united-states
python -m trending_scraper xuser --username sama naval elonmusk
python -m trending_scraper instagram --hashtag health --count 30
python -m trending_scraper youtube --region nigeria --count 50
python -m trending_scraper youtube --region nigeria --health   # health/howto category
python -m trending_scraper tiktok --mode trending --count 30
python -m trending_scraper tiktok --mode hashtag --query health
python -m trending_scraper telegram --channel channelname

# ── Read any article as clean text ────────────────────────────────────────────
python -m trending_scraper readurl "https://example.com/article"
python -m trending_scraper readurl "https://example.com/article" --limit 3000

# ── Rank and filter collected content ─────────────────────────────────────────
python -m trending_scraper report                          # today, all platforms, top 25
python -m trending_scraper report --days 7                 # last 7 days
python -m trending_scraper report --platform youtube       # one platform
python -m trending_scraper report --keyword diabetes       # filter by keyword in title/text
python -m trending_scraper report --min-pct 75             # top quartile only
python -m trending_scraper report --top 50 --days 3 --min-pct 80
```

### Example report output

```
  1,240,500  pct= 98.2  [    youtube]  Why Nigeria's Healthcare System Is Changing
                         https://www.youtube.com/watch?v=xxxxx
     84,230  pct= 94.1  [    reddit]  New drug pricing regulations — what it means
                         https://www.reddit.com/r/Health/comments/xxxxx
     12,400  pct= 91.0  [ instagram]  #health post by @username
                         https://www.instagram.com/p/xxxxx
```

---

## VPS deployment

```bash
# 1. Edit scripts/deploy_vps.sh and set your VPS hostname in the VPS= variable
# 2. Deploy code and install dependencies
bash scripts/deploy_vps.sh

# 3. Install the daily cron on the VPS (runs at 05:00 UTC)
ssh root@your-vps "cd /root/trending-scraper && bash scripts/setup_cron.sh"
```

Edit `scripts/cron_scrape.sh` to configure which subreddits, X accounts, Instagram hashtags, and YouTube regions match your use case.

## Cookie auto-refresh (Mac)

```bash
# Install launchd job — re-extracts cookies every 6 hours automatically
bash scripts/refresh_cookies.sh --install
```

---

## Project structure

```
trending_scraper/
├── __main__.py        CLI entry point (all subcommands)
├── config.py          Credential resolution (.env chain, VPS + local)
├── fetchers.py        HTTP helpers: fetch(), fetch_brightdata(), fetch_jina()
├── items.py           Normalised Item dataclass + engagement formula
├── storage.py         SQLite upsert, percentile scoring, load/query
├── doctor.py          Health check for all platforms and credentials
├── notify.py          Telegram bot alerts (failure + daily summary)
└── scrapers/
    ├── reddit.py
    ├── x.py
    ├── instagram.py
    ├── youtube.py
    ├── tiktok.py
    ├── telegram.py
    └── hackernews.py

scripts/
├── extract_cookies.py     Chrome CDP cookie extractor
├── launch_chrome_debug.sh Start Chrome with persistent debug profile
├── refresh_cookies.sh     launchd installer for 6-hour cookie refresh
├── deploy_vps.sh          rsync + pip install to VPS
├── setup_cron.sh          Install daily cron on VPS
└── cron_scrape.sh         The cron job itself (all platforms + alerts)
```

---

## Configuration reference

All keys can be set in `.env` (project root), `/root/.hermes/.env` (VPS), or `~/.hermes/.env` (Mac). Earlier files in that chain take precedence. See `.env.example` for the full list with descriptions.

---

## License

MIT
