"""Minimal OpenF1 client: throttled, retrying, with a gzip raw-response cache for incremental reruns."""
from __future__ import annotations

import gzip
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://api.openf1.org/v1/"
MIN_INTERVAL_S = float(os.environ.get("F1PIPE_MIN_INTERVAL_S", "2.1"))  # ~28 req/min, under the free-tier limit
_last = 0.0


def _throttle() -> None:
    global _last
    wait = _last + MIN_INTERVAL_S - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last = time.monotonic()


def fetch(endpoint: str, params: dict[str, Any]) -> list[dict]:
    """GET an endpoint. Returns [] when OpenF1 has no data. Backs off on 429/5xx."""
    query = "&".join(f"{k}={urllib.parse.quote(str(v), safe=':-+.')}" for k, v in params.items())
    url = f"{BASE}{endpoint}?{query}"
    for attempt in range(10):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "f1pipe/1.0 (github.com/martintxortiz/f1data)"})
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read())
            return data if isinstance(data, list) else []
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(min(120, 10 * (attempt + 1)))
                continue
            raise RuntimeError(f"HTTP {e.code} for {url}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(min(120, 5 * (attempt + 1)))
    raise RuntimeError(f"giving up on {url}")


class RawCache:
    """Raw responses stored as <root>/<session_key>/<name>.json.gz (exact API payload)."""

    def __init__(self, root: str):
        self.root = root

    def get(self, session_key: int, name: str, endpoint: str, params: dict[str, Any]) -> list[dict]:
        path = os.path.join(self.root, str(session_key), f"{name}.json.gz")
        if os.path.exists(path):
            with gzip.open(path, "rt") as f:
                return json.load(f)
        data = fetch(endpoint, params)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with gzip.open(tmp, "wt", compresslevel=6) as f:
            json.dump(data, f)
        os.replace(tmp, path)
        return data
