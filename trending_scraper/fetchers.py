"""Two fetch tiers:
  fetch()            — plain requests with a browser-ish UA (free, try first)
  fetch_brightdata() — Bright Data Web Unlocker REST API (proxied, beats most
                       bot walls, but returns server-rendered HTML only — no JS)
"""

from __future__ import annotations

import requests

from . import config

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

session = requests.Session()
session.headers["User-Agent"] = UA


def fetch(url: str, timeout: int = 30, method: str = "GET", **kwargs) -> requests.Response:
    resp = session.request(method, url, timeout=timeout, **kwargs)
    resp.raise_for_status()
    return resp


def fetch_jina(url: str, timeout: int = 30) -> str:
    """Fetch any URL via Jina Reader (r.jina.ai) — free, returns clean markdown.

    Useful for extracting article text from URLs found in trending posts.
    No JS rendering (same limitation as Bright Data) but free and fast.
    Falls back to plain fetch if Jina is unreachable.
    """
    try:
        return fetch(f"https://r.jina.ai/{url}", timeout=timeout).text
    except Exception:
        return fetch(url, timeout=timeout).text


def fetch_brightdata(url: str, timeout: int = 90) -> str:
    """Fetch a URL through Bright Data Web Unlocker. Returns the HTML body.

    Known limits (tested on the Hermes VPS): no JS rendering, so SPA-only
    pages (e.g. X Articles) come back empty; age-restricted content shows
    login walls.
    """
    api_key, zone = config.brightdata_credentials()
    if not api_key:
        raise RuntimeError(
            "No Bright Data API key found (env BRIGHT_DATA_API_KEY, .env, "
            "/root/.hermes/.env, or ~/.hermes/.env.remote-cutover)"
        )
    resp = requests.post(
        "https://api.brightdata.com/request",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"zone": zone, "format": "json", "url": url},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    status = data.get("status_code")
    if status and status >= 400:
        raise RuntimeError(f"Bright Data target returned {status} for {url}")
    return data.get("body", "")
