"""Digest feeds for watch results: RSS 2.0 and JSON Feed 1.1 files. Nothing is emailed or published."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

DISCLAIMER = ("Not investment, legal or medical advice. Data may be incomplete, delayed or wrong; "
              "PDUFA dates are unverified candidates from SEC filings.")
HOME = "https://example.invalid/biocatalystfeed"


def _title(c: dict) -> str:
    t = c.get("title") or c.get("brand") or c.get("nct_id") or c.get("key") or ""
    s = f"[{(c['severity'] + ' ') if c.get('severity') else ''}{c.get('kind') or 'change'}] {t}"
    s = s + (f": {c['field']} {c.get('old')} -> {c.get('new')}" if c.get("field") else "")
    return (f"[{c['registry_class']}] " + s) if c.get("registry_class") else s


def _body(c: dict) -> str:
    from .globalcov import GLOBAL_DISCLAIMER
    return DISCLAIMER + ("\n\n" + GLOBAL_DISCLAIMER if c.get("registry_class") else "")


def _dt(s) -> datetime:
    try:
        d = datetime.fromisoformat(str(s or "").replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _id(c: dict) -> str:
    return ":".join(str(c.get(k) or "") for k in ("watch", "id", "key", "nct_id", "kind", "field", "run_id"))


def _url(c: dict):
    if c.get("url"): return c["url"]
    if c.get("nct_id"): return f"https://clinicaltrials.gov/study/{c['nct_id']}"
    return None


def json_feed(title: str, changes: list[dict], home_url: str = HOME) -> dict:
    return {"version": "https://jsonfeed.org/version/1.1", "title": title, "home_page_url": home_url, "description": DISCLAIMER,
            "items": [{"id": _id(c), "title": _title(c), "url": _url(c), "content_text": _title(c) + "\n\n" + _body(c),
                       "date_published": _dt(c.get("detected_at")).isoformat(), "_biocatalystfeed": c} for c in changes]}


def rss(title: str, changes: list[dict], home_url: str = HOME) -> str:
    items = "".join(
        f"<item><title>{escape(_title(c))}</title>" + (f"<link>{escape(_url(c))}</link>" if _url(c) else "")
        + f'<guid isPermaLink="false">{escape(_id(c))}</guid><pubDate>{format_datetime(_dt(c.get("detected_at")))}</pubDate>'
        + f"<description>{escape(_title(c) + ' | ' + _body(c))}</description></item>" for c in changes)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            f"<title>{escape(title)}</title><link>{escape(home_url)}</link><description>{escape(DISCLAIMER)}</description>"
            f"<lastBuildDate>{format_datetime(datetime.now(timezone.utc))}</lastBuildDate>{items}</channel></rss>\n")


def _line(c: dict) -> str:
    """One digest line for a change record or an event record (readout / FDA decision / trial at risk)."""
    if c.get("detected_at") or c.get("field") or c.get("kind", "").startswith("new_"):
        return _title(c)
    d = c.get("readout_date") or c.get("date") or ""
    who = c.get("sponsor") or c.get("company") or ""
    tk = f" [{c['ticker']}]" if c.get("ticker") else ""
    risk = "; ".join(f["detail"] for f in c.get("risk_flags") or [])
    return f"{d} {c.get('kind') or ''} {c.get('phase') or ''} {who}{tk}: {c.get('title') or c.get('key') or ''}".strip() + (f" ({risk})" if risk else "")


def markdown(title: str, items: list[dict], intro: str | None = None) -> str:
    """Rendered Markdown digest (changes or events). Local output only; nothing is sent."""
    out = [f"# {title}", "", f"_Generated {datetime.now(timezone.utc).isoformat(timespec='minutes')} UTC. {len(items)} items._", ""]
    if intro: out += [intro, ""]
    for c in items:
        u = _url(c)
        out.append(f"- {_line(c).replace('[', '(').replace(']', ')')}" + (f" - [source]({u})" if u else ""))
    if not items: out.append("- No items.")
    out += ["", f"> {DISCLAIMER}", ""]
    return "\n".join(out)


def html(title: str, items: list[dict], intro: str | None = None) -> str:
    """Rendered standalone HTML digest (changes or events), email-ready inline styles. Local output only."""
    rows = "".join(f'<li style="margin:4px 0">{escape(_line(c))}' + (f' - <a href="{escape(_url(c))}">source</a>' if _url(c) else "") + "</li>" for c in items)
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title></head>'
            f'<body style="font-family:system-ui,sans-serif;max-width:860px;margin:auto;padding:16px">'
            f"<h1 style=\"font-size:20px\">{escape(title)}</h1><p style=\"color:#555\">Generated {datetime.now(timezone.utc).isoformat(timespec='minutes')} UTC. {len(items)} items.</p>"
            + (f"<p>{escape(intro)}</p>" if intro else "") + f"<ul>{rows or '<li>No items.</li>'}</ul>"
            f'<p style="color:#777;font-size:12px">{escape(DISCLAIMER)}</p></body></html>\n')


def write(changes: list[dict], title: str, rss_path: str | None = None, json_path: str | None = None,
          md_path: str | None = None, html_path: str | None = None) -> None:
    if md_path: open(md_path, "w").write(markdown(title, changes))
    if html_path: open(html_path, "w").write(html(title, changes))
    if rss_path: open(rss_path, "w").write(rss(title, changes))
    if json_path: open(json_path, "w").write(json.dumps(json_feed(title, changes), indent=1, default=str))


def add_args(p) -> None:
    p.add_argument("--rss", metavar="FILE", help="write an RSS 2.0 digest of this run's changes (local file; nothing is sent)")
    p.add_argument("--json-feed", metavar="FILE", help="write a JSON Feed 1.1 digest of this run's changes")
    p.add_argument("--digest-md", metavar="FILE", help="write a rendered Markdown digest of this run's changes")
    p.add_argument("--digest-html", metavar="FILE", help="write a rendered HTML digest (email-ready inline styles; nothing is sent)")


def add_query_args(p) -> None:
    p.add_argument("--exclude", nargs="+", metavar="TERM", help="drop results whose title/text contains any of these words/phrases")
    p.add_argument("--rank", action="store_true", help="sort by relevance to the query terms (adds a 'relevance' field)")
