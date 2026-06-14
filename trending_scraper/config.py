"""Credential/config resolution that works on both the local Mac and the
Hermes VPS without any per-machine setup.

Lookup order for each key:
  1. process environment
  2. .env next to the project root
  3. /root/.hermes/.env            (Hermes VPS)
  4. ~/.hermes/.env.remote-cutover (local copy of the VPS env)
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ENV_FILES = [
    PROJECT_ROOT / ".env",
    Path("/root/.hermes/.env"),                         # VPS
    Path.home() / ".hermes" / ".env",                  # local Hermes env (written by extract_cookies.py)
    Path.home() / ".hermes" / ".env.remote-cutover",   # legacy local copy of VPS env
]


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        lines = path.read_text(errors="ignore").splitlines()
    except OSError:
        return out
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


_file_env: dict[str, str] | None = None


def get(key: str, default: str = "") -> str:
    global _file_env
    if key in os.environ:
        return os.environ[key]
    if _file_env is None:
        _file_env = {}
        # earlier files win, so merge in reverse order
        for path in reversed(ENV_FILES):
            _file_env.update(_parse_env_file(path))
    return _file_env.get(key, default)


def brightdata_credentials() -> tuple[str, str]:
    """Returns (api_key, zone). api_key is empty if not configured."""
    return get("BRIGHT_DATA_API_KEY"), get("BRIGHT_DATA_ZONE", "web_unlocker1")
