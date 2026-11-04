"""Webhook alerts for watch runs: POST this run's changes to your own URL(s).

Nothing is sent unless you pass --webhook. Formats:
  json    : {"event": "bcf.changes", "title", "count", "sent_at", "disclaimer", "changes": [...], "feed": <JSON Feed 1.1>}
  slack   : Slack incoming-webhook payload {"text": ...} (also Mattermost / Rocket.Chat / Google Chat compatible)
  discord : Discord webhook payload {"content": ...} (2,000-character limit, truncated with a count of the rest)
If BCF_WEBHOOK_SECRET is set (or --webhook-secret-env names another variable), the json body is signed:
  X-BCF-Signature: sha256=<hex HMAC-SHA256 of the raw body with the secret>  (verify before trusting the payload)
Delivery failures are reported on stderr and never fail the watch (the snapshot is already stored).
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

FORMATS = ("json", "slack", "discord")
USER_AGENT = "BioCatalystFeed-webhook/1 (+https://biocat.ai)"
MAX_CHANGES = 500  # per POST; the rest are counted in "truncated"


def _lines(title: str, changes: list[dict], limit: int) -> str:
    from .digest import _line, _url, DISCLAIMER
    out = [f"*{title}*: {len(changes)} change(s)"]
    used = len(out[0])
    for i, c in enumerate(changes):
        u = _url(c)
        s = f"- {_line(c)}" + (f" <{u}>" if u else "")
        if used + len(s) + 80 > limit:
            out.append(f"... and {len(changes) - i} more")
            break
        out.append(s); used += len(s) + 1
    out.append(f"_{DISCLAIMER}_")
    return "\n".join(out)


def payload(title: str, changes: list[dict], fmt: str = "json") -> dict:
    from .digest import json_feed, DISCLAIMER
    if fmt == "slack":
        return {"text": _lines(title, changes, 3500)}
    if fmt == "discord":
        return {"content": _lines(title, changes, 1900)[:2000]}
    if fmt != "json":
        raise ValueError(f"unknown webhook format {fmt!r}; use one of {FORMATS}")
    keep = changes[:MAX_CHANGES]
    return {"event": "bcf.changes", "title": title, "count": len(changes), "truncated": max(0, len(changes) - len(keep)),
            "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "disclaimer": DISCLAIMER,
            "changes": keep, "feed": json_feed(title, keep)}


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _check_url(url: str) -> None:
    u = urlparse(url)
    if u.scheme not in ("https", "http") or not u.netloc:
        raise ValueError(f"webhook URL must be http(s)://...: {url!r}")


def send(urls: list[str] | None, title: str, changes: list[dict], fmt: str = "json", secret: str | None = None,
         always: bool = False, session=None, retries: int = 1, timeout: float = 15) -> list[dict]:
    """POST the changes to each URL. Returns one result dict per URL ({url, ok, status, error}). Skips when there are
    no changes unless always=True. Never raises for network errors."""
    if not urls or (not changes and not always):
        return []
    import requests
    s = session or requests.Session()
    body = json.dumps(payload(title, changes, fmt), default=str).encode()
    headers = {"content-type": "application/json", "user-agent": USER_AGENT}
    if secret and fmt == "json":
        headers["x-bcf-signature"] = sign(body, secret)
    out = []
    for url in urls:
        _check_url(url)
        res = {"url": url, "ok": False, "status": None, "error": None}
        for attempt in range(retries + 1):
            try:
                r = s.post(url, data=body, headers=headers, timeout=timeout)
                res["status"] = r.status_code
                res["ok"] = 200 <= r.status_code < 300
                if res["ok"] or r.status_code < 500 and r.status_code != 429:
                    break
            except Exception as e:  # network errors: report, don't crash the watch
                res["error"] = f"{type(e).__name__}: {e}"
            if attempt < retries:
                time.sleep(1.0)
        if not res["ok"]:
            print(f"webhook: delivery to {urlparse(url).netloc} failed (status={res['status']} {res['error'] or ''})".rstrip(),
                  file=sys.stderr)
        out.append(res)
    return out


def add_args(p) -> None:
    p.add_argument("--webhook", action="append", metavar="URL",
                   help="POST this run's changes to URL (repeatable). Only sent when there are changes (see --webhook-always)")
    p.add_argument("--webhook-format", choices=FORMATS, default="json",
                   help="json (default; signed with BCF_WEBHOOK_SECRET if set), slack or discord")
    p.add_argument("--webhook-always", action="store_true", help="also POST when the run found no changes (heartbeat)")
    p.add_argument("--webhook-secret-env", default="BCF_WEBHOOK_SECRET", metavar="VAR",
                   help="environment variable holding the HMAC secret (default BCF_WEBHOOK_SECRET)")


def from_args(a, title: str, changes: list[dict]) -> list[dict]:
    urls = getattr(a, "webhook", None)
    if not urls:
        return []
    secret = os.environ.get(getattr(a, "webhook_secret_env", None) or "BCF_WEBHOOK_SECRET")
    return send(urls, title, changes, getattr(a, "webhook_format", "json") or "json", secret,
                getattr(a, "webhook_always", False))
