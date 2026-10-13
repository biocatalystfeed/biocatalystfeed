"""SEC EDGAR: full-text search (efts.sec.gov/LATEST/search-index, the public JSON backend
used by https://www.sec.gov/edgar/search/) + submissions API (data.sec.gov) + archived filing documents.
SEC fair-access policy (https://www.sec.gov/os/accessing-edgar-data): <=10 requests/second total, declare a User-Agent
with company name + contact email. EDGAR data is public US-government information. We use 0.2 s spacing (5 req/s).
Set SEC_USER_AGENT to override the default UA. Output is UNVERIFIED regex extraction - always check the source filing."""
from __future__ import annotations
import html, os, re
from biowatch.http import Throttled
from biowatch.store import ItemStore

PLACEHOLDER_CONTACT = "contact@biocatalystfeed.invalid"  # replace via env once a product contact address is approved


def user_agent() -> str:
    """SEC asks for a User-Agent naming the organisation and a contact email. Override fully with SEC_USER_AGENT, or set
    BIOCATALYSTFEED_CONTACT to a product contact address. The default is a non-routable placeholder (no personal name)."""
    if os.environ.get("SEC_USER_AGENT"): return os.environ["SEC_USER_AGENT"]
    return f"BioCatalystFeed/0.2 {os.environ.get('BIOCATALYSTFEED_CONTACT') or PLACEHOLDER_CONTACT}"


UA = user_agent()


def not_registered_message(company: str) -> str:
    return (f"{company!r} has no SEC CIK: it looks privately held, non-US, or acquired/delisted, so it files nothing on "
            "SEC EDGAR and secwatch has nothing to search. If it is public, pass its 10-digit CIK or ticker. Its trials, "
            "FDA records, grants and papers are still available via trialwatch / fdawatch / grantwatch / paperwatch.")
EFTS = "https://efts.sec.gov/LATEST/search-index"
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
DATE_RE = re.compile(rf"\b((?:{MONTHS})\.?\s+\d{{1,2}},?\s+20\d\d|(?:{MONTHS})\s+20\d\d|\d{{1,2}}/\d{{1,2}}/20\d\d|"
                     rf"(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\s+(?:of\s+)?20\d\d|(?:Q[1-4]|[1-4]Q)\s*20\d\d|"
                     rf"(?:first|second|early|mid|late|end of)[\s-]+(?:half\s+(?:of\s+)?)?20\d\d)\b", re.I)
NOYEAR_RE = re.compile(rf"\b((?:{MONTHS})\.?\s+\d{{1,2}})\b(?!,?\s*\d)")
PDUFA_RE = re.compile(r"PDUFA|Prescription Drug User Fee Act|target action date|goal date", re.I)
TRACKED = ("candidates",)
LABEL = "UNVERIFIED - regex extraction from SEC filing text; confirm in the linked document before use"


class SECClient(Throttled):
    def __init__(self, **kw):
        super().__init__(min_interval=kw.pop("min_interval", 0.2), user_agent=kw.pop("user_agent", None) or user_agent(), **kw)

    def fts(self, q: str, ciks: list[str] | None = None, forms: str = "8-K", since: str | None = None,
            until: str | None = None, max_hits: int = 100) -> list[dict]:
        out, frm = [], 0
        while len(out) < max_hits:
            p = {"q": q, "forms": forms, "from": frm}
            if ciks: p["ciks"] = ",".join(c.zfill(10) for c in ciks)
            if since or until: p.update(dateRange="custom", startdt=since or "2001-01-01", enddt=until or "2100-01-01")
            d = self.get_json(EFTS, params=p)
            hits = d.get("hits", {}).get("hits", [])
            out += hits; frm += len(hits)
            if not hits or frm >= d.get("hits", {}).get("total", {}).get("value", 0): break
        return out[:max_hits]

    def submissions(self, cik: str) -> dict:
        return self.get_json(f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json")

    def text(self, url: str) -> str:
        r = self.request("GET", url); r.raise_for_status()
        t = re.sub(r"(?is)<(script|style).*?</\1>", " ", r.text)
        t = re.sub(r"(?s)<[^>]+>", " ", t)
        return re.sub(r"\s+", " ", html.unescape(t).replace("\xa0", " "))

    def ticker_cik(self, ticker: str) -> str | None:
        d = self.get_json("https://www.sec.gov/files/company_tickers.json")
        return next((str(v["cik_str"]) for v in d.values() if v["ticker"].upper() == ticker.upper()), None)


def doc_url(hit: dict) -> str:
    adsh, fn = hit["_id"].split(":", 1)
    cik = str(int(hit["_source"]["ciks"][0]))
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{fn}"


def extract_candidates(text: str, window: int = 250, max_gap: int = 120) -> list[dict]:
    """Dates (or quarters/halves) close to a PDUFA/goal-date mention. A date must lie within `max_gap` chars of the
    mention (after it, or up to 60 chars before) and the nearest one per mention is flagged best=True. 'Month D' without
    a year is kept with year_inferred=True (caller can fill it from the filing date)."""
    out, seen = [], {}
    for m in PDUFA_RE.finditer(text):
        a, b = max(0, m.start() - 60), min(len(text), m.end() + window)
        seg = text[a:b]
        found = []
        for d in list(DATE_RE.finditer(seg)) + list(NOYEAR_RE.finditer(seg)):
            gap = d.start() - (m.end() - a) if d.start() >= m.end() - a else (m.start() - a) - d.end()
            if gap > max_gap or gap < -5: continue
            val = re.sub(r"\s+", " ", d.group(1)).strip()
            if any(val in f["date_text"] and val != f["date_text"] for f in found): continue
            ctx = text[max(0, m.start() - 150): min(len(text), m.end() + 200)].strip()
            found.append({"date_text": val, "gap_chars": gap, "year_inferred": not re.search(r"20\d\d", val), "context": ctx})
        found = [f for f in found if not any(f["date_text"] in g["date_text"] and f is not g for g in found)]
        found.sort(key=lambda f: f["gap_chars"])
        for i, f in enumerate(found):
            f["best"] = i == 0
            k = f["date_text"].lower()
            if k not in seen: seen[k] = f; out.append(f)
            elif f["best"]: seen[k]["best"] = True
    return out


def infer_year(md: str, file_date: str | None) -> str | None:
    """'March 14' + filing 2024-01-08 -> '2024-03-14' (next year if the month/day already passed at filing)."""
    from datetime import datetime
    if not file_date: return None
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            y = int(file_date[:4]); d = datetime.strptime(f"{md.replace('.', '').replace('Sept', 'Sep')} {y}", fmt).date()
            if d.isoformat() < file_date: d = d.replace(year=y + 1)
            return d.isoformat()
        except ValueError:
            continue
    return None


def pdufa_mentions(client: SECClient, cik: str, since: str | None = None, until: str | None = None,
                   max_docs: int = 15) -> list[dict]:
    hits = client.fts('"PDUFA"', ciks=[cik], forms="8-K", since=since, until=until, max_hits=max_docs)
    hits.sort(key=lambda h: h["_source"].get("file_date", ""), reverse=True)
    rows = []
    for h in hits[:max_docs]:
        s, url = h["_source"], doc_url(h)
        try:
            cands = extract_candidates(client.text(url))
            for c in cands:
                if c.get("year_inferred"): c["date_guess"] = infer_year(c["date_text"], s.get("file_date"))
        except Exception as e:  # pragma: no cover
            cands = [{"date_text": None, "context": f"fetch failed: {e}"}]
        rows.append({"key": h["_id"], "company": (s.get("display_names") or [""])[0], "form": s.get("form"),
                     "file_type": s.get("file_type"), "file_date": s.get("file_date"), "items": s.get("items"),
                     "title": f"{s.get('form')} {s.get('file_type')} filed {s.get('file_date')}", "url": url,
                     "filing_index": f"https://www.sec.gov/Archives/edgar/data/{int(s['ciks'][0])}/{s['adsh'].replace('-', '')}/",
                     "candidates": cands, "status": LABEL})
    return rows


def company_sec(client: SECClient, alias: dict, since: str | None = None, max_docs: int = 10) -> dict | None:
    cik = alias.get("sec_cik")
    if not cik and alias.get("ticker") and "." not in alias["ticker"]:  # 'ZEAL.CO' = non-US listing
        cik = client.ticker_cik(alias["ticker"])
    if not cik:
        return {"not_sec_registered": True, "message": not_registered_message(alias.get("canonical") or "company"), "label": LABEL}
    sub = client.submissions(cik)
    rec = sub.get("filings", {}).get("recent", {})
    eightk = [(d, a) for f, d, a in zip(rec.get("form", []), rec.get("filingDate", []), rec.get("accessionNumber", [])) if f == "8-K"]
    return {"cik": str(cik), "name": sub.get("name"), "tickers": sub.get("tickers"),
            "recent_8k_count": len(eightk), "latest_8k": eightk[0][0] if eightk else None,
            "pdufa_mentions": pdufa_mentions(client, str(cik), since=since, max_docs=max_docs), "label": LABEL}


def store(path: str) -> ItemStore:
    return ItemStore(path, "sec", TRACKED, new_kind="new_pdufa_filing")


def run_watch(client: SECClient, st: ItemStore, watch: str, cik: str, since: str | None = None, max_docs: int = 25) -> dict:
    rows = pdufa_mentions(client, cik, since=since, max_docs=max_docs)
    for r in rows: r["candidates"] = sorted({c["date_text"] for c in r["candidates"] if c["date_text"]})
    info = st.ingest(watch, rows, query={"cik": cik, "since": since})
    info["changes_detail"] = st.changes(watch=watch, run_id=info["run_id"])
    return info
