"""Minimal openFDA client (public, no key). Terms: https://open.fda.gov/terms/ (data CC0 unless marked).
Limits without key: 240 req/min and 1,000 req/day per IP (open.fda.gov/apis/authentication). We throttle to ~1 req/s,
back off on 429/5xx, and treat 404 NOT_FOUND as an empty result."""
from __future__ import annotations
import os
import time
import requests
from biowatch.http import retry_delay, is_retryable

BASE = "https://api.fda.gov"
UA = "BioCatalystFeed-fdawatch/0.2"
PAGE = 100           # openFDA max limit per request for these endpoints is 1000; 100 keeps payloads small
MAX_SKIP = 25000     # openFDA hard cap on skip


def quote(v: str) -> str:
    return '"' + v.replace('"', "") + '"'


def date_range(since: str | None, until: str | None = None) -> str:
    s = (since or "19000101").replace("-", "")
    u = (until or "29991231").replace("-", "")
    return f"[{s}+TO+{u}]"


class OpenFDAClient:
    def __init__(self, min_interval: float = 1.0, session: requests.Session | None = None, api_key: str | None = None):
        self.min_interval = min_interval
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = UA
        self.api_key = api_key or os.environ.get("OPENFDA_API_KEY") or None
        self._last = 0.0
        self.calls = 0

    def _get(self, path: str, search: str, limit: int, skip: int = 0, sort: str | None = None) -> dict:
        # openFDA wants literal '+' as space separators; build the query string by hand so requests doesn't encode them
        qs = f"search={search}&limit={limit}&skip={skip}"
        if sort: qs += f"&sort={sort}"
        if self.api_key: qs += f"&api_key={self.api_key}"
        for attempt in range(4):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0: time.sleep(wait)
            self._last = time.monotonic(); self.calls += 1
            try:
                r = self.s.get(f"{BASE}{path}?{qs}", timeout=60)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 3: raise
                time.sleep(retry_delay(attempt, base=3.0)); continue
            if r.status_code == 404:
                return {"results": [], "meta": {"results": {"total": 0}}}
            if is_retryable(r) and attempt < 3:
                time.sleep(retry_delay(attempt, r, base=3.0)); continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return {}

    def query(self, path: str, search: str, max_records: int = 500, sort: str | None = None) -> list[dict]:
        out: list[dict] = []
        skip = 0
        while len(out) < max_records and skip <= MAX_SKIP:
            d = self._get(path, search, min(PAGE, max_records - len(out)), skip, sort)
            res = d.get("results", [])
            out.extend(res)
            total = d.get("meta", {}).get("results", {}).get("total", 0)
            skip += len(res)
            if not res or skip >= total: break
        return out

    # --- endpoints -------------------------------------------------------------
    def drugsfda(self, sponsors: list[str] | None = None, application_number: str | None = None,
                 since: str | None = None, until: str | None = None, max_records: int = 500) -> list[dict]:
        return self.query("/drug/drugsfda.json", build_drugsfda_search(sponsors, application_number, since, until), max_records)

    def labels(self, manufacturers: list[str] | None = None, since: str | None = None, until: str | None = None,
               max_records: int = 200) -> list[dict]:
        return self.query("/drug/label.json", build_label_search(manufacturers, since, until), max_records,
                          sort="effective_time:desc")


def _or(field: str, values: list[str]) -> str:
    return "(" + "+OR+".join(f"{field}:{quote(v)}" for v in values) + ")"


def build_drugsfda_search(sponsors=None, application_number=None, since=None, until=None) -> str:
    parts = []
    if sponsors: parts.append(_or("sponsor_name", sponsors))
    if application_number: parts.append(f"application_number:{quote(application_number.upper())}")
    if since or until: parts.append(f"submissions.submission_status_date:{date_range(since, until)}")
    if not parts: raise ValueError("need sponsors, application_number or a date range")
    return "+AND+".join(parts)


def build_label_search(manufacturers=None, since=None, until=None) -> str:
    parts = []
    if manufacturers: parts.append(_or("openfda.manufacturer_name", manufacturers))
    if since or until: parts.append(f"effective_time:{date_range(since, until)}")
    if not parts: raise ValueError("need manufacturers or a date range")
    return "+AND+".join(parts)
