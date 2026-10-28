"""FDA decision tracking: one calendar of upcoming and recent FDA decision events, each with provenance + confidence.

Event kinds (all public sources; nothing scraped from sites that disallow it):
  pdufa     Upcoming PDUFA / target action dates DISCLOSED BY COMPANIES in SEC 8-K filings (EDGAR full-text search,
            efts.sec.gov). FDA does not publish PDUFA dates; these are regex extractions from company text.
            confidence = "company-disclosed" (unverified extraction; always read the linked filing).
  adcom     FDA advisory committee meetings from Federal Register notices. confidence = "scheduled" (official notice).
  approval  Approvals (original applications and efficacy supplements) from Drugs@FDA via openFDA. confidence = "confirmed".
  crl       Complete response letters from openFDA. confidence = "confirmed" (published by FDA, with a lag).
Every event carries: kind, date, date_precision (day / month / quarter / half / year), confidence, company, ticker,
drug, title, url (official record), provenance {source, field, method, retrieved}. Scheduling/reference data, not
investment advice.

Filters: drug (name or code), company (name or ticker; alias-resolved), condition (free text), since/until (event
date), upcoming_days, kinds. `condition` is matched against the text each source carries (8-K text near the PDUFA
mention, AdCom agenda, CRL letter, Drugs@FDA pharmacologic class); Drugs@FDA has no indication field, so condition
filtering of approvals is coarse.
Watching: snapshots go to the local DB (prefix `fdadec`); a later run reports new events and changed dates/status
(e.g. a PDUFA date moved by a new 8-K, an AdCom postponed)."""
from __future__ import annotations
import re
from datetime import date, timedelta
from biowatch import filters
from biowatch.store import ItemStore

KINDS = ("pdufa", "adcom", "approval", "crl")
TRACKED = ("date", "status", "confidence")
SEC_SOURCE = "SEC EDGAR full-text search (company 8-K filings); public U.S. government data"
CONFIDENCE = {"pdufa": "company-disclosed", "adcom": "scheduled", "approval": "confirmed", "crl": "confirmed"}
MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
DRUG_SUFFIX = (r"mab|nib|tide|stat|parin|ase|cel|gene|vec|lisib|mer|tinib|ciclib|vir|pril|sartan|afil|gliflozin|glutide|"
               r"sentan|lukast|platin|rsen|siran|tug|cept|kin|pant|zole|done|pine|lone|sone|xaban|gatran|mide|plimab")
DRUG_RE = re.compile(rf"\b([A-Z][A-Za-z0-9-]{{2,}}®?\s*\(([a-z][a-z-]{{4,}})\)|[a-z]{{3,}}(?:{DRUG_SUFFIX})(?:-[a-z]{{4}})?)\b")
TICKER_RE = re.compile(r"\(([A-Z.\-]{1,6})(?:,\s*[A-Z.\-]{1,6})*\)\s*\(CIK (\d+)\)")


def today_iso() -> str:
    return date.today().isoformat()


def parse_when(text: str | None, guess: str | None = None) -> tuple[str | None, str | None]:
    """'March 14, 2027' -> ('2027-03-14','day'); 'March 2027' -> ('2027-03-01','month'); 'Q2 2027' / 'second quarter of
    2027' -> ('2027-04-01','quarter'); 'first half 2027' -> ('2027-01-01','half'); '3/14/2027' -> day."""
    if guess: return guess, "day"
    t = (text or "").strip().lower().replace(".", "")
    if not t: return None, None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(20\d\d)", t)
    if m: return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}", "day"
    m = re.fullmatch(r"([a-z]{3})[a-z]*\s+(\d{1,2}),?\s+(20\d\d)", t)
    if m and m.group(1) in MONTHS: return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}", "day"
    m = re.fullmatch(r"([a-z]{3})[a-z]*\s+(20\d\d)", t)
    if m and m.group(1) in MONTHS: return f"{m.group(2)}-{MONTHS[m.group(1)]:02d}-01", "month"
    q = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}
    m = re.search(r"(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\s+(?:of\s+)?(20\d\d)", t) or \
        re.search(r"(?:q([1-4])|([1-4])q)\s*(20\d\d)", t)
    if m:
        g = m.groups()
        n = q.get(g[0]) if len(g) == 2 else int(g[0] or g[1])
        y = g[-1]
        return f"{y}-{(n - 1) * 3 + 1:02d}-01", "quarter"
    m = re.search(r"(first|early|second|mid|late|end of)[\s-]+(?:half\s+(?:of\s+)?)?(20\d\d)", t)
    if m: return (f"{m.group(2)}-01-01" if m.group(1) in ("first", "early") else f"{m.group(2)}-07-01"), "half"
    return None, None


def drug_of(context: str) -> str | None:
    """Best-effort drug name near a PDUFA mention: 'Brand (generic)' or an INN-looking word."""
    m = DRUG_RE.search(context or "")
    if not m: return None
    return m.group(2) and f"{m.group(0).split('(')[0].strip()} ({m.group(2)})" or m.group(0)


def resolve_company(company: str | None, sec=None) -> dict | None:
    """Alias table first; a bare ticker that the table doesn't know is looked up in SEC's company_tickers.json."""
    if not company: return None
    from fdawatch.aliases import resolve
    al = resolve(company)
    if not al["known"] and sec is not None and re.fullmatch(r"[A-Z.\-]{1,6}", company.strip()):
        try:
            d = sec.get_json("https://www.sec.gov/files/company_tickers.json")
            hit = next((v for v in d.values() if v["ticker"].upper() == company.strip().upper()), None)
            if hit:
                name = hit["title"]
                al = dict(resolve(name), canonical=name, ticker=company.strip().upper(), sec_cik=str(hit["cik_str"]),
                          fda_sponsors=[name.split()[0].upper()])
        except Exception:
            pass
    return al


def _hit(text: str, term: str | None) -> bool:
    return not term or filters._hit((text or "").lower(), term)


def _ev(kind, d, prec, company, ticker, drug, title, url, status, prov, key, **extra) -> dict:
    return {"key": key, "kind": kind, "date": d, "date_precision": prec, "confidence": CONFIDENCE[kind],
            "status": status, "company": company, "ticker": ticker, "drug": drug, "title": title, "url": url,
            "provenance": prov, **extra}


def pdufa_events(sec, drug=None, al=None, condition=None, filed_since=None, max_docs=20, today=None) -> list[dict]:
    """PDUFA / target action dates from company 8-Ks. One event per (company, drug, date) - the newest filing wins."""
    from secwatch.core import doc_url, extract_candidates, infer_year
    today = today or today_iso()
    q = '"PDUFA"' + (f' "{drug}"' if drug else "") + (f' "{condition}"' if condition else "")
    cik = (al or {}).get("sec_cik")
    if al and not cik and al.get("ticker") and "." not in al["ticker"]:
        try: cik = sec.ticker_cik(al["ticker"])
        except Exception: cik = None
    if al and al.get("known") and not cik: return []
    filed_since = filed_since or (date.fromisoformat(today) - timedelta(days=365)).isoformat()
    hits = sec.fts(q, ciks=[cik] if cik else (None if not al else None), forms="8-K", since=filed_since, max_hits=max_docs * 2)
    if al and not cik:  # unknown company without CIK: filter by display name
        k = al["canonical"].lower().split()[0]
        hits = [h for h in hits if k in " ".join(h["_source"].get("display_names") or []).lower()]
    hits.sort(key=lambda h: h["_source"].get("file_date", ""), reverse=True)
    out: dict[str, dict] = {}
    for h in hits[:max_docs]:
        s, url = h["_source"], doc_url(h)
        dn = (s.get("display_names") or [""])[0]
        m = TICKER_RE.search(dn)
        company = re.sub(r"\s*\(.*$", "", dn).strip() or None
        ticker = m.group(1) if m else None
        try: text = sec.text(url)
        except Exception: continue
        for c in extract_candidates(text):
            if not c.get("best") or not c.get("date_text"): continue
            guess = infer_year(c["date_text"], s.get("file_date")) if c.get("year_inferred") else None
            d, prec = parse_when(c["date_text"], guess)
            if not d: continue
            ctx = c.get("context") or ""
            dg = drug_of(ctx)
            if drug and not _hit(ctx, drug) and not _hit(dg or "", drug):
                if not _hit(text, drug): continue
                dg = dg or drug
            if condition and not _hit(text, condition): continue
            if re.search(r"\b(approved|approval of)\b.{0,40}\b(on|in)\b", ctx, re.I) and d < s.get("file_date", ""):
                continue  # past action date described retrospectively
            k = f"pdufa:{(m.group(2) if m else company or '').lstrip('0')}:{(dg or drug or 'unknown').lower()}"
            ev = _ev("pdufa", d, prec, company, ticker, dg or drug, f"PDUFA {c['date_text']} - {company}" + (f" ({dg})" if dg else ""),
                     url, "pending" if d >= today else "date_passed",
                     {"source": SEC_SOURCE, "field": "8-K text near 'PDUFA' / 'target action date'",
                      "method": "regex extraction (UNVERIFIED) - read the filing", "filed": s.get("file_date"),
                      "form": s.get("form"), "retrieved": today}, k, date_text=c["date_text"], context=ctx[:400])
            if k not in out: out[k] = ev  # hits are newest-filed first
    return list(out.values())


def adcom_events(fr, drug=None, al=None, condition=None, since=None, today=None, max_records=100) -> list[dict]:
    from adcomwatch.core import meetings, SOURCE
    today = today or today_iso()
    rows = meetings(fr, since=since or (date.fromisoformat(today) - timedelta(days=365)).isoformat(), max_records=max_records, today=today)
    out = []
    names = [al["canonical"], *(al.get("aka") or [])] if al else []
    for r in rows:
        hay = " ".join(str(r.get(f) or "") for f in ("title", "agenda", "sponsors"))
        if drug and not _hit(hay, drug): continue
        if names and not any(_hit(hay, n) for n in names): continue
        if condition and not _hit(hay, condition): continue
        status = {"postponement": "postponed", "cancellation": "cancelled"}.get(r.get("kind"), "scheduled")
        d = r.get("meeting_date")
        out.append(_ev("adcom", d, "day" if d else None, r.get("sponsors"), al.get("ticker") if al else None, drug,
                       f"AdCom {d or '?'}: {r['committee']}" + (f" - {r['applications']}" if r.get("applications") else ""),
                       r.get("url"), status if (d or "") >= today or status != "scheduled" else "held",
                       {"source": SOURCE, "field": "DATES / agenda of the Notice of Meeting", "method": "parsed from the official notice",
                        "published": r.get("published"), "retrieved": today}, f"adcom:{r['key']}",
                       committee=r["committee"], applications=r.get("applications"), agenda=(r.get("agenda") or "")[:400] or None))
    return out


def approval_events(fda, drug=None, al=None, condition=None, since=None, until=None, today=None) -> list[dict]:
    from fdawatch.core import fda_approvals
    today = today or today_iso()
    since = since or (date.fromisoformat(today) - timedelta(days=90)).isoformat()
    if drug and not al and hasattr(fda, "query"):  # search Drugs@FDA by name instead of scanning recent applications
        from fdawatch.client import quote
        from fdawatch.normalize import submissions
        t = quote(drug).replace(" ", "+")
        apps = fda.query("/drug/drugsfda.json", f'(openfda.generic_name:"{t}"+OR+openfda.brand_name:"{t}"+OR+products.brand_name:"{t}"+OR+products.active_ingredients.name:"{t}")', max_records=100)
        rows = [r for a in apps for r in submissions(a) if since <= (r["submission_status_date"] or "") <= (until or "9999") + "z"]
    else:
        rows = fda_approvals(fda, sponsor=al["canonical"] if al else None, since=since, until=until)
    out = []
    for r in rows:
        if r["submission_status"] != "APPROVED": continue
        if not (r["submission_type"] == "ORIG" or "EFFIC" in (r.get("submission_class") or "").upper()): continue
        nm = f"{r.get('brand_names') or ''} {r.get('active_ingredients') or ''}"
        if drug and not _hit(nm, drug): continue
        if condition and not _hit(f"{nm} {r.get('pharm_class') or ''}", condition): continue
        out.append(_ev("approval", r["submission_status_date"], "day", r["sponsor"], al.get("ticker") if al else None,
                       r.get("brand_names") or r.get("active_ingredients"),
                       f"Approved {r['submission_status_date']}: {r.get('brand_names') or ''} ({r['application_number']} {r['submission_type']}{r['submission_number'] or ''})",
                       r["url"], "approved",
                       {"source": "Drugs@FDA via openFDA (public domain)", "field": "submissions.submission_status_date",
                        "method": "official record", "retrieved": today}, f"approval:{r['key']}",
                       application=r["application_number"], submission_class=r.get("submission_class"),
                       review_priority=r.get("review_priority")))
    return out


def crl_events(fda, drug=None, al=None, condition=None, since=None, until=None, today=None) -> list[dict]:
    from crlwatch.core import letters, SOURCE
    today = today or today_iso()
    company = None
    if al: company = [*(al.get("fda_sponsors") or []), al["canonical"]] if al.get("known") else [al["canonical"]]
    rows = letters(fda, since=since or (date.fromisoformat(today) - timedelta(days=365)).isoformat(), until=until,
                   company=company, keyword=drug or condition, max_records=200)
    if drug and condition:
        rows = [r for r in rows if _hit(f"{r.get('product')} {r.get('excerpt')}", condition)]
    return [_ev("crl", r["letter_date"], "day", r["company"], al.get("ticker") if al else None, r.get("product"),
                f"CRL {r['letter_date']}: {r['company']} {r['applications'] or ''}" + (f" ({r['product']})" if r.get("product") else ""),
                r["url"], "approved_since" if r.get("application_status") == "Approved" else "complete_response",
                {"source": SOURCE, "field": "letter_date", "method": "official record (published with a lag)", "retrieved": today},
                f"crl:{r['key']}", applications=r.get("applications"), topics=r.get("topics")) for r in rows]


def decisions(fda=None, fr=None, sec=None, kinds=None, drug=None, company=None, condition=None, since=None, until=None,
              upcoming_days=None, max_records=100, max_docs=20, today=None, errors=None) -> list[dict]:
    """Merged FDA decision events, upcoming first (soonest), then past (newest). upcoming_days limits to events from
    today to today+N (pdufa, adcom). since/until bound the event date. Failing sources are reported in `errors`."""
    kinds = [kinds] if isinstance(kinds, str) else list(kinds or KINDS)
    bad = [k for k in kinds if k not in KINDS]
    if bad: raise ValueError(f"kinds must be among {', '.join(KINDS)}")
    today = today or today_iso()
    if upcoming_days is not None:
        since, until = today, (date.fromisoformat(today) + timedelta(days=int(upcoming_days))).isoformat()
        kinds = [k for k in kinds if k in ("pdufa", "adcom")]
    al = resolve_company(company, sec)
    errors = errors if errors is not None else []
    evs: list[dict] = []
    jobs = {"pdufa": lambda: pdufa_events(sec, drug, al, condition, max_docs=max_docs, today=today),
            "adcom": lambda: adcom_events(fr, drug, al, condition, today=today),
            "approval": lambda: approval_events(fda, drug, al, condition, since=since if since and since < today else None, until=until, today=today),
            "crl": lambda: crl_events(fda, drug, al, condition, since=since if since and since < today else None, until=until, today=today)}
    for k in kinds:
        try: evs += jobs[k]()
        except Exception as e:  # one failing source must not hide the others
            errors.append({"kind": k, "error": f"{type(e).__name__}: {e}"[:300]})
    if since: evs = [e for e in evs if (e["date"] or "") >= since]
    if until: evs = [e for e in evs if (e["date"] or "9999") <= until]
    up = sorted([e for e in evs if (e["date"] or "") >= today], key=lambda e: e["date"])
    past = sorted([e for e in evs if (e["date"] or "") < today], key=lambda e: e["date"] or "", reverse=True)
    return (up + past)[:max_records]


def store(path: str) -> ItemStore:
    return ItemStore(path, "fdadec", TRACKED, new_kind="new_decision_event")


def run_watch(fda, fr, sec, st: ItemStore, watch: str, **kw) -> dict:
    kw.setdefault("max_records", 500)
    errors: list = []
    rows = decisions(fda, fr, sec, errors=errors, **kw)
    for r in rows: r["provenance"] = {k: v for k, v in r["provenance"].items() if k != "retrieved"}
    info = st.ingest(watch, rows, query={k: v for k, v in kw.items() if k != "today"})
    info["changes_detail"] = st.changes(watch=watch, run_id=info["run_id"])
    info["errors"] = errors
    return info
