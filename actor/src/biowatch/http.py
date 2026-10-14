"""Polite throttled HTTP client: min interval between requests, retry/backoff on 429/5xx."""
from __future__ import annotations
import random, time
import requests

DEFAULT_UA = "BioCatalystFeed/0.2 (+https://biocatalystfeed.com)"
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_WAIT = 60.0


def retry_delay(attempt: int, r: requests.Response | None = None, base: float = 2.0) -> float:
    """Seconds to wait before retry `attempt` (0-based): honour a numeric Retry-After (capped), else exponential
    backoff with full jitter so many clients hitting the same upstream at once don't retry in lockstep."""
    if r is not None:
        ra = r.headers.get("Retry-After", "")
        if ra.strip().isdigit():
            return min(float(ra), MAX_WAIT)
    return min(MAX_WAIT, base * 2 ** attempt) * (0.5 + random.random() / 2)


def is_retryable(r: requests.Response) -> bool:
    return r.status_code in RETRY_STATUS


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
            try:
                r = self.s.request(method, url, **kw)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 3: raise
                time.sleep(retry_delay(attempt)); continue
            if is_retryable(r) and attempt < 3:
                time.sleep(retry_delay(attempt, r)); continue
            return r
        return r

    def get_json(self, url: str, **kw):
        r = self.request("GET", url, **kw); r.raise_for_status(); return r.json()

    def post_json(self, url: str, payload: dict):
        r = self.request("POST", url, json=payload); r.raise_for_status(); return r.json()
