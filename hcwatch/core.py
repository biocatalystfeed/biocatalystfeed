"""Health Canada Notices of Compliance (NOC): Canadian drug and biologic approvals, newest first.

Source: Health Canada, Notice of Compliance Database API (https://health-products.canada.ca/api/notice-of-compliance/,
documented at https://health-products.canada.ca/api/documentation/noc-documentation-en.html). Updated nightly; human
drugs from 1994. Contains information licensed under the Open Government Licence - Canada
(https://open.canada.ca/en/open-government-licence-canada).

A NOC means Health Canada authorised a submission: a new drug (NDS), an abbreviated/generic one (ANDS), or a supplement
(SNDS / SANDS: new indication, new strength, labelling, manufacturing ...). A NOC/c ("with conditions") requires
confirmatory studies. The API serves whole tables only (no date filter), so the three tables used here (NOC main,
drug products, medicinal ingredients; ~50 MB together) are cached locally for 24 h and filtered locally.
"""
from __future__ import annotations
import json, os, time, urllib.request
from datetime import date, timedelta
from biowatch import filters
from biowatch.store import ItemStore

BASE = "https://health-products.canada.ca/api/notice-of-compliance/{t}/?lang=en&type=json"
TABLES = ("noticeofcompliancemain", "drugproduct", "medicinalingredient")
PAGE = "https://health-products.canada.ca/noc-ac/nocInfo?lang=eng&no={n}"
SOURCE = ("Health Canada, Notice of Compliance Database (health-products.canada.ca/api/notice-of-compliance); "
          "contains information licensed under the Open Government Licence - Canada")
UA = "BioCatalystFeed (https://github.com/biocatalystfeed/biocatalystfeed; contact@biocat.ai)"
TRACKED = ("date", "active", "with_conditions", "brand_names", "ingredients")
# The API truncates submission type labels to 20 characters.
SUBMISSIONS = {"New Drug Submission": "NDS", "Supplement to a New": "SNDS", "Abbreviated New Drug": "ANDS",
               "Supplement to an Abb": "SANDS"}
SUB_CODES = ("NDS", "SNDS", "ANDS", "SANDS")
NAS_CLASSES = ("New Active Substance", "Priority-NAS")


class NOCClient:
    """Downloads and caches the NOC API tables; `tables()` returns {table_name: [rows]}."""

    def __init__(self, cache_dir: str | None = None, max_age_hours: float = 24, base: str = BASE, timeout: int = 180):
        self.dir = cache_dir or os.path.expanduser("~/.cache/biocatalystfeed")
        self.max_age, self.base, self.timeout = max_age_hours * 3600, base, timeout
        self._tables = None

    def fetch(self, table: str) -> list:
        path = os.path.join(self.dir, f"hc_noc_{table}.json")
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < self.max_age:
            with open(path, "rb") as f: return json.loads(f.read())
        req = urllib.request.Request(self.base.format(t=table), headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r: data = r.read()
        try: rows = json.loads(data)
        except ValueError: raise RuntimeError(f"Health Canada NOC API ({table}) did not return JSON")
        if not isinstance(rows, list): raise RuntimeError(f"Health Canada NOC API ({table}) returned an unexpected shape")
        os.makedirs(self.dir, exist_ok=True)
        with open(path + ".tmp", "wb") as f: f.write(data)
        os.replace(path + ".tmp", path)
        return rows

    def tables(self) -> dict:
        if self._tables is None: self._tables = {t: self.fetch(t) for t in TABLES}
        return self._tables


def _add(d: dict, k, v):
    v = (v or "").strip() if isinstance(v, str) else v
    if v:
        lst = d.setdefault(k, [])
        if v not in lst: lst.append(v)


def records(tables: dict) -> list[dict]:
    """One record per NOC, joined with brand names / DINs and medicinal ingredients. Newest first."""
    brands, dins, ingr = {}, {}, {}
    for p in tables.get("drugproduct", []):
        _add(brands, p.get("noc_number"), p.get("noc_br_brandname")); _add(dins, p.get("noc_number"), p.get("noc_br_din"))
    for i in tables.get("medicinalingredient", []):
        _add(ingr, i.get("noc_number"), i.get("noc_pi_medic_ingr_name"))
    out = []
    for r in tables["noticeofcompliancemain"]:
        n = r.get("noc_number")
        if n is None: continue
        st = (r.get("noc_on_submission_type") or "").strip()
        cls = (r.get("noc_submission_class") or "").strip()
        reason = " / ".join(x.strip().replace("\n", "; ") for x in (r.get("noc_reason_submission"), r.get("noc_reason_supplement")) if x and x.strip())
        rec = {"key": f"hcnoc:{n}", "noc_number": n, "date": r.get("noc_date"), "manufacturer": r.get("noc_manufacturer_name"),
               "submission": SUBMISSIONS.get(st, st or None), "submission_class": cls or None,
               "supplement": r.get("noc_is_suppliment") == "Y", "administrative": r.get("noc_is_admin") == "Y" or cls == "Admin",
               "with_conditions": r.get("noc_status_with_conditions") == "Y",
               "new_active_substance": cls in NAS_CLASSES, "priority": cls.startswith("Priority"),
               "product_type": r.get("noc_product_type"), "active": r.get("noc_active_status") != "0",
               "reason": reason or None, "therapeutic_class": (r.get("noc_therapeutic_class") or "").strip() or None,
               "reference_product": " / ".join(x for x in (r.get("noc_crp_product_name"), r.get("noc_crp_company_name"),
                                                           r.get("noc_crp_country_name")) if x) or None,
               "brand_names": sorted(brands.get(n, [])), "dins": sorted(dins.get(n, [])), "ingredients": sorted(ingr.get(n, [])),
               "url": PAGE.format(n=n), "source": SOURCE}
        label = "; ".join(rec["brand_names"][:3]) or "; ".join(rec["ingredients"][:3]) or f"NOC {n}"
        tags = [rec["submission"] or "NOC"] + (["NAS"] if rec["new_active_substance"] else []) + (["NOC/c"] if rec["with_conditions"] else [])
        rec["title"] = f"{label} ({rec['manufacturer']}) Health Canada {' '.join(tags)} {rec['date']}"
        out.append(rec)
    return sorted(out, key=lambda x: (x["date"] or "", x["noc_number"]), reverse=True)


def _match(v, terms) -> bool:
    text = " ".join(v) if isinstance(v, list) else (v or "")
    return any(filters._hit(text.lower(), t) for t in terms)


def notices(client, company=None, ingredient=None, brand=None, submission=None, keyword: str | None = None,
            since: str | None = None, until: str | None = None, recent_days: int | None = None,
            new_active_substance: bool = False, with_conditions: bool = False, priority: bool = False,
            include_admin: bool = False, include_veterinary: bool = False, exclude=None, max_records: int = 100,
            today_: str | None = None) -> list[dict]:
    """Health Canada NOCs, newest first. Administrative NOCs (name/ownership changes) and veterinary drugs are dropped
    unless asked for. submission: any of NDS, SNDS, ANDS, SANDS."""
    L = lambda x: [x] if isinstance(x, str) else list(x or [])
    subs = [s.upper() for s in L(submission)]
    bad = [s for s in subs if s not in SUB_CODES]
    if bad: raise ValueError(f"submission must be among {', '.join(SUB_CODES)}")
    if recent_days is not None:
        lo = (date.fromisoformat(today_ or date.today().isoformat()) - timedelta(days=int(recent_days))).isoformat()
        since = max(since, lo) if since else lo
    out = []
    for r in records(client.tables()):
        if since and (r["date"] or "") < since: continue
        if until and (r["date"] or "") > until: continue
        if subs and r["submission"] not in subs: continue
        if not include_admin and r["administrative"]: continue
        if not include_veterinary and r["product_type"] == "Veterinary": continue
        if new_active_substance and not r["new_active_substance"]: continue
        if with_conditions and not r["with_conditions"]: continue
        if priority and not r["priority"]: continue
        if company and not _match(r["manufacturer"], L(company)): continue
        if ingredient and not _match(r["ingredients"], L(ingredient)): continue
        if brand and not _match(r["brand_names"], L(brand)): continue
        if keyword and not _match(" ".join(str(r[f] or "") if not isinstance(r[f], list) else " ".join(r[f]) for f in
                                           ("brand_names", "ingredients", "manufacturer", "reason", "therapeutic_class")), [keyword]): continue
        out.append(r)
    out = filters.exclude(out, exclude, fields=("brand_names", "ingredients", "manufacturer", "reason"))
    return out[:max_records]


def store(path: str) -> ItemStore:
    return ItemStore(path, "hcnoc", TRACKED, new_kind="new_noc")


def run_watch(client, st: ItemStore, watch: str, **kw) -> dict:
    kw.setdefault("max_records", 100000)
    if not kw.get("since") and kw.get("recent_days") is None: kw["recent_days"] = 365  # bounded window; older NOCs rarely change
    rows = notices(client, **kw)
    info = st.ingest(watch, rows, query=kw)
    info["changes_detail"] = st.changes(watch=watch, run_id=info["run_id"])
    return info
