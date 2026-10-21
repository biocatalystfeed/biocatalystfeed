"""FDA advisory committee (AdCom) meeting notices from the Federal Register API (federalregister.gov/api/v1).

Source: the Federal Register, published by the Office of the Federal Register (National Archives) and the U.S.
Government Publishing Office. Documented public JSON API, no key. Federal Register documents are U.S. government works
(public domain). An AdCom meeting is a dated catalyst: the notice names the committee, the meeting date and, for drug
and biologics committees, usually the application (NDA/BLA number), product and sponsor under discussion.
"""
from __future__ import annotations
import html, re
from datetime import date
from biowatch import filters
from biowatch.http import Throttled
from biowatch.store import ItemStore

API = "https://www.federalregister.gov/api/v1/documents.json"
SOURCE = "Federal Register (federalregister.gov), Office of the Federal Register; FDA notices"
FIELDS = ("title", "document_number", "publication_date", "dates", "html_url", "raw_text_url", "action", "docket_ids", "abstract")
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_RE = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})")
APP_RE = re.compile(r"\b(s?NDA|s?BLA|ANDA|PMA|De Novo)\)?\s*(?:No\.\s*)?(\d{6}(?:/S-\d+)?)", re.I)
SPONSOR_RE = re.compile(r"\b(?:submitted by|from)\s+([A-Z][A-Za-z0-9&.,'()\- ]+?)(?=,\s+(?:for|to)\b|[;:]|\.\s|\s+for\s|\s+to\s|\s+The\s|$)")
BOILERPLATE = re.compile(r"The meeting presentations will be heard, viewed, captioned,? and recorded through an online "
                         r"teleconferencing and/or video conferencing platform\.\s*", re.I)
AREAS = ("drugs", "biologics", "devices", "tobacco", "other")
# Notices about a specific meeting; nominations, renewals, charters and RFIs are dropped.
KIND_RULES = (("cancel", "cancellation"), ("postpone", "postponement"), ("amendment of notice", "amendment"),
              ("notice of meeting", "meeting"), ("notice of public meeting", "meeting"))
TRACKED = ("meeting_date", "kind", "title", "applications", "sponsors")


class FRClient:
    def __init__(self, http: Throttled | None = None):
        self.http = http or Throttled(min_interval=1.0)

    def documents(self, since: str | None = None, until: str | None = None, max_pages: int = 5) -> list[dict]:
        """FDA notices mentioning 'advisory committee', newest first (100 per page)."""
        p = [("conditions[agencies][]", "food-and-drug-administration"), ("conditions[type][]", "NOTICE"),
             ("conditions[term]", '"advisory committee"'), ("order", "newest"), ("per_page", "100")]
        p += [("fields[]", f) for f in FIELDS]
        if since: p.append(("conditions[publication_date][gte]", since))
        if until: p.append(("conditions[publication_date][lte]", until))
        out = []
        for page in range(1, max_pages + 1):
            d = self.http.get_json(API, params=p + [("page", str(page))])
            out += d.get("results") or []
            if page >= (d.get("total_pages") or 1): break
        return out

    def full_text(self, url: str) -> str:
        r = self.http.request("GET", url); r.raise_for_status(); return r.text


def kind_of(title: str, abstract: str | None = None) -> str | None:
    t = (title or "").lower()
    if "advisory committee" not in t and "panel" not in t: return None
    if "amendment to the notice of meeting" in (abstract or "").lower(): return "amendment"
    for needle, kind in KIND_RULES:
        if needle in t: return kind
    return None


def area_of(committee: str) -> str:
    c = (committee or "").lower()
    if "tobacco" in c: return "tobacco"
    if "device" in c or "panel of the" in c or "radiological" in c: return "devices"
    if any(x in c for x in ("vaccines", "biological", "cellular, tissue", "blood products", "gene therap", "allergenic")): return "biologics"
    if "drug" in c or "compounding" in c or "nonprescription" in c: return "drugs"
    return "other"


def iso_dates(text: str | None) -> list[str]:
    out = []
    for m, d, y in DATE_RE.findall(text or ""):
        try:
            v = date(int(y), MONTHS.split("|").index(m) + 1, int(d)).isoformat()
        except ValueError:
            continue
        if v not in out: out.append(v)
    return out


def plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or ""))


def agenda_of(text: str) -> str | None:
    """The 'Agenda:' section of a meeting notice minus the standard webcast sentence (whitespace collapsed, capped at
    1,500 characters). Takes a second paragraph when the first one is only that boilerplate."""
    t = plain(text)
    m = re.search(r"Agenda:\s*(.+)", t, re.S)
    if not m: return None
    paras = [re.sub(r"\s+", " ", BOILERPLATE.sub("", re.sub(r"\s+", " ", x))).strip()
             for x in re.split(r"\n {3,}(?=\S)|\n\s*\n", m.group(1))[:3]]
    out = ""
    for x in paras:
        if x.startswith(("FDA intends", "Procedure:")): break
        out = (out + " " + x).strip()
        if len(out) >= 60: break
    return out[:1500] or None


def dates_of(text: str) -> str | None:
    """The DATES section, else the first 'will/would be held on <date>' sentence (amendment notices)."""
    t = plain(text)
    m = re.search(r"DATES:\s*(.+?)(?:\n\s*\n|$)", t, re.S) or re.search(rf"((?:will|would) be held on\s+(?:{MONTHS})\s+\d{{1,2}},\s+\d{{4}})", t)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def _app(a: str) -> str:
    a = a.upper()
    return "De Novo" if a == "DE NOVO" else ("s" + a[1:] if a.startswith("S") else a)


def normalize(doc: dict, agenda: str | None = None) -> dict:
    title = (doc.get("title") or "").strip()
    committee = title.split(";")[0].strip()
    dates = iso_dates(doc.get("dates")) or iso_dates(agenda)
    hay = f"{title.replace('--', ' ')} {agenda or ''}"
    apps = sorted({f"{_app(a)} {n}" for a, n in APP_RE.findall(hay)})
    sponsors = sorted({re.sub(r"\b(Inc|Ltd|Corp|Co)$", r"\1.", re.sub(r"\s+", " ", s).strip().rstrip(".,"))
                       for s in SPONSOR_RE.findall(re.sub(r"\bFrom\b", "from", hay))
                       if len(s) < 100 and s.split()[0] not in ("FDA", "The", "January", "February", "March", "April", "May",
                                                                 "June", "July", "August", "September", "October", "November", "December")})
    return {"key": doc.get("document_number"), "document_number": doc.get("document_number"), "title": title,
            "committee": committee, "area": area_of(committee), "kind": kind_of(title, doc.get("abstract")),
            "published": doc.get("publication_date"), "meeting_date": dates[0] if dates else None,
            "meeting_dates": dates, "dates_text": (doc.get("dates") or "").strip()[:500] or None,
            "agenda": agenda, "applications": ", ".join(apps) or None, "sponsors": "; ".join(sponsors) or None,
            "docket": ", ".join(doc.get("docket_ids") or []) or None, "url": doc.get("html_url"),
            "date": dates[0] if dates else doc.get("publication_date"), "source": SOURCE}


def meetings(client: FRClient, since: str | None = None, until: str | None = None, area=None, committee=None,
             keyword=None, upcoming: bool = False, agenda: bool = True, exclude=None, rank: bool = False,
             max_records: int = 100, today: str | None = None, max_pages: int = 5) -> list[dict]:
    """Meeting notices (meeting / amendment / postponement / cancellation), newest meeting first. area defaults to
    everything except tobacco. agenda=True fetches each notice's full text (1 request each) for the agenda."""
    areas = [area] if isinstance(area, str) else list(area or [a for a in AREAS if a != "tobacco"])
    today = today or date.today().isoformat()
    rows = []
    for d in client.documents(since=since, until=until, max_pages=max_pages):
        if not kind_of(d.get("title"), d.get("abstract")): continue
        n = normalize(d)
        if n["area"] not in areas: continue
        if committee and committee.lower() not in n["committee"].lower(): continue
        if upcoming and not (n["meeting_date"] and n["meeting_date"] >= today): continue
        rows.append((d, n))
    rows.sort(key=lambda x: (x[1]["date"] or "", x[1]["key"] or ""), reverse=True)
    out = []
    for d, n in rows:
        if len(out) >= max_records and not keyword: break
        if agenda and d.get("raw_text_url") and n["kind"] in ("meeting", "amendment"):
            try:
                txt = client.full_text(d["raw_text_url"])
                n = normalize(dict(d, dates=d.get("dates") or dates_of(txt)), agenda_of(txt))
            except Exception:  # agenda is best-effort; the notice itself is still useful
                pass
        if keyword and not filters._hit(" ".join(str(n.get(f) or "") for f in ("title", "agenda", "sponsors")).lower(), keyword):
            continue
        out.append(n)
    out = filters.exclude(out, exclude, fields=("title", "committee", "agenda", "sponsors"))
    if rank: out = filters.rank(out, keyword, committee)
    return out[:max_records]


def store(path: str) -> ItemStore:
    return ItemStore(path, "adcom", TRACKED, new_kind="new_notice")


def run_watch(client: FRClient, st: ItemStore, watch: str, **kw) -> dict:
    kw.setdefault("max_records", 500)
    rows = meetings(client, **kw)
    for r in rows: r.pop("relevance", None)
    info = st.ingest(watch, rows, query={k: v for k, v in kw.items() if k != "today"})
    info["changes_detail"] = st.changes(watch=watch, run_id=info["run_id"])
    return info
