"""iCalendar (RFC 5545) export for dated event records: trial readouts (primary completion dates) and FDA decision events
(PDUFA / AdCom / approval / CRL). One all-day VEVENT per record, stable UID (re-importing updates instead of duplicating),
source link in URL and DESCRIPTION, ESTIMATED / company-disclosed labels kept in the summary. Local output only; nothing
is published. Subscribe to a hosted copy (e.g. https://biocat.ai/calendar/calendar.ics) in Google / Apple / Outlook."""
from __future__ import annotations
import hashlib
from datetime import date, datetime, timedelta, timezone

PRODID = "-//BioCatalystFeed//bcf//EN"
DISCLAIMER = "Scheduling/reference data from public records; dates can move. Not investment, legal or medical advice."


def _esc(s) -> str:
    return str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Fold to 75 octets per RFC 5545 3.1 without splitting a UTF-8 character."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode()); cur = b""
        cur += b
    out.append(cur.decode())
    return "\r\n ".join(out)


def _day(s) -> date | None:
    s = str(s or "")
    try:
        if len(s) >= 10: return date.fromisoformat(s[:10])
        if len(s) == 7: return date.fromisoformat(s + "-01")
    except ValueError:
        return None
    return None


def _summary(e: dict) -> str:
    who = e.get("ticker") or e.get("sponsor") or e.get("company") or ""
    if e.get("nct_id") and (e.get("kind") in (None, "readout") or "readout_date" in e):
        est = "" if e.get("readout_date_type") == "ACTUAL" else " (est.)"
        ph = (e.get("phase") or "").replace("PHASE", "P").replace("|", "/").replace(", ", "/")
        return f"{who} {ph} readout{est}: {e.get('acronym') or e.get('title') or e['nct_id']}".strip()
    kind = (e.get("kind") or "event").upper()
    conf = f" ({e['confidence']})" if e.get("confidence") and e.get("confidence") != "confirmed" else ""
    return f"{who} {kind}{conf}: {e.get('drug') or e.get('title') or ''}".strip()


def _uid(e: dict) -> str:
    k = e.get("key") or e.get("id") or e.get("nct_id") or repr(sorted((k, str(v)) for k, v in e.items()))
    return hashlib.sha1(str(k).encode()).hexdigest()[:20] + "@biocat.ai"


def event_lines(e: dict, stamp: str) -> list[str]:
    d = _day(e.get("readout_date") or e.get("date"))
    if not d: return []
    url = e.get("url") or e.get("source_url") or (f"https://clinicaltrials.gov/study/{e['nct_id']}" if e.get("nct_id") else "")
    desc = [e.get("title") or ""]
    if e.get("nct_id"): desc.append(f"{e['nct_id']} | {e.get('phase') or ''} | {e.get('status') or ''} | sponsor: {e.get('sponsor') or ''}")
    if e.get("readout_date_type"): desc.append(f"Primary completion date ({e['readout_date_type']}); top-line results usually follow later.")
    if e.get("confidence"): desc.append(f"Confidence: {e['confidence']}")
    if e.get("date_precision") and e["date_precision"] != "day": desc.append(f"Date precision: {e['date_precision']} (shown on the first day)")
    if e.get("ticker"): desc.append(f"Ticker {e['ticker']} (confidence {e.get('ticker_confidence')})")
    if url: desc.append(f"Source: {url}")
    desc.append(DISCLAIMER)
    lines = ["BEGIN:VEVENT", f"UID:{_uid(e)}", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{d:%Y%m%d}",
             f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}", f"SUMMARY:{_esc(_summary(e))}",
             f"DESCRIPTION:{_esc(chr(10).join(x for x in desc if x))}", "TRANSP:TRANSPARENT"]
    if url: lines.append(f"URL:{url}")
    cats = [c for c in (e.get("kind") or ("readout" if e.get("nct_id") else ""), e.get("readout_date_type") or e.get("confidence")) if c]
    if cats: lines.append(f"CATEGORIES:{','.join(_esc(c) for c in cats)}")
    return lines + ["END:VEVENT"]


def calendar(title: str, events: list[dict], now: datetime | None = None) -> str:
    """Whole VCALENDAR text (CRLF line endings). Records without a usable date are skipped."""
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_esc(title)}", f"X-WR-CALDESC:{_esc(DISCLAIMER)}", "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
             "X-PUBLISHED-TTL:PT12H"]
    for e in events: lines += event_lines(e, stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def write(path: str, title: str, events: list[dict]) -> None:
    with open(path, "w", newline="") as f: f.write(calendar(title, events))
