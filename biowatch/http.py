"""Polite throttled HTTP client: min interval between requests, retry/backoff on 429/5xx."""
from __future__ import annotations
import time
import requests

DEFAULT_UA = "BioCatalystFeed/0.2 (+https://example.invalid/biocatalystfeed)"


class Throttled:
    def __init__(self, min_interval: float = 1.0, user_agent: str = DEFAULT_UA, session: requests.Session | None = None):
        self.min_interval = min_interval
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = user_agent
        self._last = 0.0
        self.calls = 0

    def request(self, method: str, url: str, **kw) -> requests.Response:
        kw.setdefault("timeout", 60)
        r = None
        for attempt in range(4):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0: time.sleep(wait)
            self._last = time.monotonic(); self.calls += 1
            r = self.s.request(method, url, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(3 * (attempt + 1)); continue
            return r
        return r

    def get_json(self, url: str, **kw):
        r = self.request("GET", url, **kw); r.raise_for_status(); return r.json()

    def post_json(self, url: str, payload: dict):
        r = self.request("POST", url, json=payload); r.raise_for_status(); return r.json()
