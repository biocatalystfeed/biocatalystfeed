"""FDA orphan drug designations and approvals (OOPD searchable designation database), newest first.

Source: U.S. Food and Drug Administration, Office of Orphan Products Development, "Orphan Drug Designations and
Approvals" database (https://www.accessdata.fda.gov/scripts/opdlisting/oopd/). FDA's instructions page documents that a
search with no criteria returns all designations, and the search form offers "Download Excel file" as an output format;
that download (an HTML table served as application/msexcel, ~9 MB / ~8,300 rows from 1983, about 2 s) is the only thing
fetched here: one POST of the public form with a descriptive User-Agent, cached locally for 24 h. No browser
User-Agent, cookies or session handling. U.S. government work, public domain (FDA website policies).

One row in FDA's file per (designation, orphan approval); rows sharing FDA's record key ("CF Grid Key", which FDA notes is
for its own purposes) are merged into one record per designation with a list of approvals. That key also addresses the
public detail page (detailedIndex.cfm?cfgridkey=...). Street addresses are not copied (city / state / country only).
Withdrawn/revoked dates are shown by FDA only for designations withdrawn after 2013-08-12, and exclusivity-protected
indications only for approvals from 2013-01-01.
"""
from __future__ import annotations
import html as _html, json, os, re, time, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta
from biowatch import filters
from biowatch.store import ItemStore

SEARCH_URL = "https://www.accessdata.fda.gov/scripts/opdlisting/oopd/OOPD_Results.cfm"
PAGE = "https://www.accessdata.fda.gov/scripts/opdlisting/oopd/detailedIndex.cfm?cfgridkey={k}"
SOURCE = ("U.S. FDA Office of Orphan Products Development, Orphan Drug Designations and Approvals database "
          "(accessdata.fda.gov/scripts/opdlisting/oopd); U.S. government work, public domain")
UA = "BioCatalystFeed (https://github.com/biocatalystfeed/biocatalystfeed; contact@biocat.ai)"
CAVEAT = ("An orphan designation is not an approval and says nothing about efficacy; FDA lists withdrawn/revoked dates "
          "only from 2013-08-12 and exclusivity-protected indications only for approvals from 2013-01-01.")
COLS = {"generic": "Generic Name", "trade": "Trade Name", "designated": "Date Designated", "designation": "Orphan Designation",
        "status": "Orphan Designation Status", "withdrawn": "Date Designation Withdrawn or Revoked",
        "approval_status": "FDA Orphan Approval Status", "indication": "Approved Labeled Indication",
        "approved": "Marketing Approval Date", "excl_end": "Exclusivity End Date", "excl_ind": "Exclusivity Protected Indication",
        "sponsor": "Sponsor Company", "city": "Sponsor City", "state": "Sponsor State", "country": "Sponsor Country",
        "grid": "CF Grid Key"}
STATUSES = ("designated", "approved", "withdrawn")
DATE_BY = ("designated", "approved", "withdrawn", "any")
TRACKED = ("status", "approved", "withdrawn", "withdrawn_date", "approval_dates", "exclusivity_ends", "trade_names", "sponsor")


def form(start: str = "01/01/1983", end: str | None = None) -> dict:
    """The public search form with no criteria (= all designations), Excel output."""
    return {"Product_name": "", "sponsor_name": "", "Designation": "", "Designation_Start_Date": start,
            "Designation_End_Date": end or date.today().strftime("%m/%d/%Y"), "Search_param": "DESDATE",
            "Output_Format": "Excel", "Sort_order": "Date_Reverse_Order", "RecordsPerPage": "25", "newSearch": "Run Search"}


class OOPDClient:
    """Downloads the full designation table once a day; `rows()` returns FDA's rows as dicts keyed by column name."""

    def __init__(self, cache_dir: str | None = None, max_age_hours: float = 24, url: str = SEARCH_URL, timeout: int = 180):
        self.dir = cache_dir or os.path.expanduser("~/.cache/biocatalystfeed")
        self.cache = os.path.join(self.dir, "fda_oopd.html")
        self.max_age, self.url, self.timeout = max_age_hours * 3600, url, timeout
        self._rows = None

    def _get(self) -> bytes:
        body = urllib.parse.urlencode(form()).encode()
        for attempt in (0, 1):
            req = urllib.request.Request(self.url, data=body, method="POST",
                                         headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r: return r.read()
            except urllib.error.HTTPError as e:
                if attempt or e.code not in (401, 403, 429, 500, 502, 503, 504): raise
                time.sleep(2)

    def fetch(self) -> bytes:
        if os.path.exists(self.cache) and time.time() - os.path.getmtime(self.cache) < self.max_age:
            with open(self.cache, "rb") as f: return f.read()
        data = self._get()
        if not looks_like_oopd(data):
            raise RuntimeError("FDA orphan designation download did not return the expected table (blocked or format changed?)")
        os.makedirs(self.dir, exist_ok=True)
        with open(self.cache + ".tmp", "wb") as f: f.write(data)
        os.replace(self.cache + ".tmp", self.cache)
        return data

    def rows(self) -> list[dict]:
        if self._rows is None: self._rows = parse_table(self.fetch().decode("utf-8", "replace"))
        return self._rows


def looks_like_oopd(data: bytes) -> bool:
    head = data[:3000].decode("utf-8", "replace")
    return "<table" in head.lower() and COLS["designation"] in head and COLS["sponsor"] in head


def _cell(c: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", c))).strip()


def parse_table(text: str) -> list[dict]:
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I)
    if not trs: raise RuntimeError("FDA orphan designation table has no rows (format changed?)")
    head = [_cell(c) for c in re.findall(r"<th[^>]*>(.*?)</th>", trs[0], re.S | re.I)]
    idx = {}
    for k, name in COLS.items():
        hit = [i for i, h in enumerate(head) if h == name or (k == "excl_ind" and h.startswith(name))]
        if not hit and k not in ("city", "state"): raise RuntimeError(f"FDA orphan designation table is missing column '{name}'")
        if hit: idx[k] = hit[0]
    out = []
    for tr in trs[1:]:
        cells = [_cell(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
        if len(cells) < len(head): continue
        out.append({k: cells[i] for k, i in idx.items()})
    return out


def iso(d: str | None) -> str | None:
    m = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*", d or "")
    return f"{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}" if m else None


def records(rows: list[dict]) -> list[dict]:
    """One record per designation (FDA record key), approvals merged; newest event first."""
    by = {}
    for r in rows:
        k = r.get("grid") or f"{r.get('generic')}|{r.get('designated')}|{r.get('designation')}"
        rec = by.get(k)
        if rec is None:
            st = r.get("status") or ""
            rec = by[k] = {"key": f"oopd:{k}", "grid_key": r.get("grid") or None, "generic_name": r.get("generic") or None,
                           "trade_names": [], "designation": r.get("designation") or None,
                           "designated_date": iso(r.get("designated")), "status": st or None,
                           "approved": "Approved" in st, "withdrawn": "Withdrawn" in st or "Revoked" in st,
                           "withdrawn_date": iso(r.get("withdrawn")), "approvals": [],
                           "sponsor": r.get("sponsor") or None,
                           "sponsor_location": ", ".join(x for x in (r.get("city"), r.get("state"), r.get("country")) if x) or None,
                           "sponsor_country": r.get("country") or None,
                           "url": PAGE.format(k=r["grid"]) if r.get("grid") else None, "source": SOURCE}
        t = r.get("trade")
        if t and t not in rec["trade_names"]: rec["trade_names"].append(t)
        ad = iso(r.get("approved"))
        if ad or r.get("indication"):
            a = {"date": ad, "indication": r.get("indication") or None, "exclusivity_end": iso(r.get("excl_end")),
                 "exclusivity_indication": r.get("excl_ind") or None, "trade_name": t or None}
            if a not in rec["approvals"]: rec["approvals"].append(a)
    out = []
    for rec in by.values():
        rec["approvals"].sort(key=lambda a: a["date"] or "", reverse=True)
        rec["trade_names"].sort()
        rec["approval_dates"] = sorted({a["date"] for a in rec["approvals"] if a["date"]})
        rec["exclusivity_ends"] = sorted({a["exclusivity_end"] for a in rec["approvals"] if a["exclusivity_end"]})
        rec["latest_approval_date"] = rec["approval_dates"][-1] if rec["approval_dates"] else None
        rec["state"] = "withdrawn" if rec["withdrawn"] else "approved" if rec["approved"] else "designated"
        rec["date"] = max(d for d in (rec["designated_date"], rec["latest_approval_date"], rec["withdrawn_date"], "") if d is not None) or None
        name = rec["generic_name"] or "unnamed product"
        if rec["trade_names"]: name += f" ({'; '.join(rec['trade_names'][:2])})"
        rec["title"] = f"{name}: FDA orphan {rec['state']} for {rec['designation'] or '?'} ({rec['sponsor'] or '?'}) {rec['date'] or ''}".strip()
        out.append(rec)
    return sorted(out, key=lambda x: (x["date"] or "", x["key"]), reverse=True)


def _L(x): return [x] if isinstance(x, str) else list(x or [])


def _match(v, terms) -> bool:
    text = (" ".join(v) if isinstance(v, list) else (v or "")).lower()
    return any(filters._hit(text, t) for t in terms)


def _lo(since, recent_days, today_):
    if recent_days is not None:
        lo = (date.fromisoformat(today_ or date.today().isoformat()) - timedelta(days=int(recent_days))).isoformat()
        return max(since, lo) if since else lo
    return since


def designations(client, company=None, product=None, condition=None, status=None, keyword: str | None = None,
                 since: str | None = None, until: str | None = None, recent_days: int | None = None, date_by: str = "designated",
                 country=None, exclude=None, max_records: int = 100, today_: str | None = None) -> list[dict]:
    """Orphan designations, newest first (by the date chosen in date_by). status: any of designated (active, not yet
    approved), approved, withdrawn. date_by: designated | approved | withdrawn | any (latest event)."""
    sts = [s.lower() for s in _L(status)]
    if any(s not in STATUSES for s in sts): raise ValueError(f"status must be among {', '.join(STATUSES)}")
    if date_by not in DATE_BY: raise ValueError(f"date_by must be one of {', '.join(DATE_BY)}")
    since = _lo(since, recent_days, today_)
    field = {"designated": "designated_date", "approved": "latest_approval_date", "withdrawn": "withdrawn_date", "any": "date"}[date_by]
    out = []
    for r in records(client.rows()):
        d = r[field]
        if date_by == "approved" and (since or until):  # any approval of this designation in the window
            ds = [x for x in r["approval_dates"] if (not since or x >= since) and (not until or x <= until)]
            if not ds: continue
        else:
            if (since or until) and not d: continue
            if since and d < since: continue
            if until and d > until: continue
        if sts and r["state"] not in sts and not ("approved" in sts and r["approved"]): continue
        if company and not _match(r["sponsor"], _L(company)): continue
        if product and not _match([r["generic_name"] or ""] + r["trade_names"], _L(product)): continue
        if condition and not _match([r["designation"] or ""] + [a["indication"] or "" for a in r["approvals"]], _L(condition)): continue
        if country and not _match(r["sponsor_country"], _L(country)): continue
        if keyword and not _match([r["generic_name"] or "", r["designation"] or "", r["sponsor"] or ""] + r["trade_names"]
                                  + [a["indication"] or "" for a in r["approvals"]], [keyword]): continue
        out.append(r)
    if date_by != "designated": out.sort(key=lambda x: (x[field] or "", x["key"]), reverse=True)
    out = filters.exclude(out, exclude, fields=("generic_name", "trade_names", "designation", "sponsor"))
    return out[:max_records]


def exclusivities(client, company=None, product=None, since: str | None = None, until: str | None = None,
                  upcoming_days: int | None = None, include_expired: bool = False, exclude=None, max_records: int = 100,
                  today_: str | None = None) -> list[dict]:
    """Orphan-drug exclusivity (7 years from approval) end dates, one row per approval, soonest first."""
    today = today_ or date.today().isoformat()
    if not since and not include_expired: since = today
    if upcoming_days is not None:
        hi = (date.fromisoformat(today) + timedelta(days=int(upcoming_days))).isoformat()
        until = min(until, hi) if until else hi
    out = []
    for r in records(client.rows()):
        if company and not _match(r["sponsor"], _L(company)): continue
        if product and not _match([r["generic_name"] or ""] + r["trade_names"], _L(product)): continue
        for a in r["approvals"]:
            e = a["exclusivity_end"]
            if not e or (since and e < since) or (until and e > until): continue
            out.append({"key": f"{r['key']}:{a['date']}", "exclusivity_end": e, "approval_date": a["date"],
                        "generic_name": r["generic_name"], "trade_name": a["trade_name"], "sponsor": r["sponsor"],
                        "protected_indication": a["exclusivity_indication"] or a["indication"], "designation": r["designation"],
                        "title": f"{a['trade_name'] or r['generic_name']} orphan exclusivity ends {e} ({r['sponsor']})",
                        "url": r["url"], "source": SOURCE})
    out.sort(key=lambda x: (x["exclusivity_end"], x["key"]))
    out = filters.exclude(out, exclude, fields=("generic_name", "trade_name", "sponsor", "protected_indication"))
    return out[:max_records]


def store(path: str) -> ItemStore:
    return ItemStore(path, "oopd", TRACKED, new_kind="new_designation")


def run_watch(client, st: ItemStore, watch: str, **kw) -> dict:
    """Snapshot every matching designation (all dates by default, so approvals of old designations show as changes)."""
    kw.setdefault("max_records", 100000)
    rows = designations(client, **kw)
    info = st.ingest(watch, rows, query=kw)
    info["changes_detail"] = st.changes(watch=watch, run_id=info["run_id"])
    return info
