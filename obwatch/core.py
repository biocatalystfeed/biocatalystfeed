"""FDA Orange Book patents and exclusivities: loss-of-exclusivity (LOE) dates per NDA/ANDA.

Source: U.S. Food and Drug Administration, "Approved Drug Products with Therapeutic Equivalence Evaluations" (Orange
Book) data files, a monthly ZIP at https://www.fda.gov/media/76860/download (products.txt, patent.txt, exclusivity.txt,
'~'-delimited). U.S. government work, public domain. Patents are those the applicant listed with FDA; FDA does not
check their validity or scope, and listed expiry dates exclude patent term not yet granted or litigation outcomes.
Exclusivity codes (NCE, ODE, PED, NP, M-xx, D-xxx, PC, CGT, GAIN ...) are FDA's; see the Orange Book preface.

A patent number ending in '*PED' is the six-month pediatric extension of that patent and is reported as its own
listing (`pediatric: true`). The ZIP is cached locally (default 24 h) so a watch downloads it at most once a day.
"""
from __future__ import annotations
import io, os, re, time, urllib.request, zipfile
from datetime import date, datetime, timedelta
from biowatch import filters
from biowatch.store import ItemStore

URL = "https://www.fda.gov/media/76860/download"
PAGE = "https://www.accessdata.fda.gov/scripts/cder/ob/results_product.cfm?Appl_Type={t}&Appl_No={n}"
SOURCE = "U.S. Food and Drug Administration, Orange Book data files (fda.gov/media/76860); public domain"
TRACKED = ("expires", "delisted", "drug_substance", "drug_product", "use_codes")
KINDS = ("patent", "exclusivity")
UA = "BioCatalystFeed (https://github.com/biocatalystfeed/biocatalystfeed; contact@biocat.ai)"
APP_RE = re.compile(r"^(?:(NDA|ANDA|N|A)\s*)?(\d{1,6})$", re.I)


class OrangeBookClient:
    """Downloads and caches the Orange Book ZIP; `tables()` returns {'products': [...], 'patent': [...], 'exclusivity': [...]}."""

    def __init__(self, cache_dir: str | None = None, max_age_hours: float = 24, url: str = URL, timeout: int = 120):
        self.cache = os.path.join(cache_dir or os.path.expanduser("~/.cache/biocatalystfeed"), "orangebook.zip")
        self.max_age, self.url, self.timeout = max_age_hours * 3600, url, timeout
        self._tables = None

    def fetch(self) -> bytes:
        if os.path.exists(self.cache) and time.time() - os.path.getmtime(self.cache) < self.max_age:
            with open(self.cache, "rb") as f: return f.read()
        req = urllib.request.Request(self.url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=self.timeout) as r: data = r.read()
        if not data.startswith(b"PK"): raise RuntimeError("Orange Book download did not return a ZIP file")
        os.makedirs(os.path.dirname(self.cache), exist_ok=True)
        with open(self.cache + ".tmp", "wb") as f: f.write(data)
        os.replace(self.cache + ".tmp", self.cache)
        return data

    def tables(self) -> dict:
        if self._tables is None: self._tables = parse_zip(self.fetch())
        return self._tables


def parse_table(text: str) -> list[dict]:
    lines = [l for l in text.replace("\r\n", "\n").split("\n") if l.strip()]
    if not lines: return []
    head = [h.strip() for h in lines[0].split("~")]
    return [dict(zip(head, (v.strip() for v in l.split("~")))) for l in lines[1:]]


def parse_zip(data: bytes) -> dict:
    out = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            base = os.path.basename(n).lower()
            for t in ("products", "patent", "exclusivity"):
                if base == f"{t}.txt": out[t] = parse_table(z.read(n).decode("latin-1"))
    missing = {"products", "patent", "exclusivity"} - set(out)
    if missing: raise RuntimeError(f"Orange Book ZIP is missing {', '.join(sorted(missing))}.txt")
    return out


def iso(d: str | None) -> str | None:
    """'Feb 24, 2027' -> '2027-02-24'; anything else (e.g. 'Approved Prior to Jan 1, 1982') -> None."""
    try: return datetime.strptime((d or "").strip(), "%b %d, %Y").date().isoformat()
    except ValueError: return None


def _app(t: str, n: str) -> str:
    return f"{'NDA' if t == 'N' else 'ANDA' if t == 'A' else t} {n}"


def parse_application(a: str) -> tuple[str | None, str]:
    m = APP_RE.match((a or "").strip())
    if not m: raise ValueError("application must look like 'NDA 020610', 'ANDA 215328' or '020610'")
    t = (m.group(1) or "").upper()
    return ({"NDA": "N", "N": "N", "ANDA": "A", "A": "A"}.get(t), m.group(2).zfill(6))


def listings(tables: dict) -> list[dict]:
    """One record per (application, patent or exclusivity code), merged over the application's product numbers."""
    prod: dict = {}
    for p in tables["products"]:
        k = (p.get("Appl_Type"), p.get("Appl_No"))
        d = prod.setdefault(k, {"trade_names": [], "ingredients": [], "applicant": p.get("Applicant_Full_Name") or p.get("Applicant"),
                                "rx_otc": set()})
        for f, src in (("trade_names", "Trade_Name"), ("ingredients", "Ingredient")):
            v = (p.get(src) or "").strip()
            if v and v not in d[f]: d[f].append(v)
        if p.get("Type"): d["rx_otc"].add(p["Type"])
    merged: dict = {}
    for kind, rows in (("patent", tables["patent"]), ("exclusivity", tables["exclusivity"])):
        for r in rows:
            t, n = r.get("Appl_Type"), r.get("Appl_No")
            code = r.get("Patent_No") if kind == "patent" else r.get("Exclusivity_Code")
            exp = iso(r.get("Patent_Expire_Date_Text") if kind == "patent" else r.get("Exclusivity_Date"))
            if not (t and n and code): continue
            key = f"ob:{t}{n}:{kind}:{code}"
            m = merged.get(key)
            if m is None:
                info = prod.get((t, n), {})
                m = merged[key] = {"key": key, "kind": kind, "code": code, "application": _app(t, n), "appl_type": t,
                                   "appl_no": n, "trade_name": "; ".join(info.get("trade_names", [])) or None,
                                   "ingredient": "; ".join(info.get("ingredients", [])) or None,
                                   "applicant": info.get("applicant"), "products": [], "expires": exp,
                                   "pediatric": kind == "patent" and code.endswith("*PED") or kind == "exclusivity" and code.startswith("PED")}
                if kind == "patent":
                    m.update(drug_substance=False, drug_product=False, use_codes=[], delisted=False,
                             submitted=iso(r.get("Submission_Date")))
            pn = r.get("Product_No")
            if pn and pn not in m["products"]: m["products"].append(pn)
            if exp and (m["expires"] is None or exp > m["expires"]): m["expires"] = exp
            if kind == "patent":
                m["drug_substance"] |= r.get("Drug_Substance_Flag") == "Y"
                m["drug_product"] |= r.get("Drug_Product_Flag") == "Y"
                m["delisted"] |= r.get("Delist_Flag") == "Y"
                u = r.get("Patent_Use_Code")
                if u and u not in m["use_codes"]: m["use_codes"].append(u)
                s = iso(r.get("Submission_Date"))
                if s and (not m["submitted"] or s < m["submitted"]): m["submitted"] = s
    for m in merged.values():
        m["products"].sort(); m["use_codes"] = sorted(m.get("use_codes", [])) if m["kind"] == "patent" else None
        what = f"patent {m['code']}" if m["kind"] == "patent" else f"exclusivity {m['code']}"
        m["title"] = " ".join(x for x in (m["trade_name"] or m["ingredient"] or m["application"], f"({m['application']})",
                                           what, "expires", m["expires"] or "?") if x)
        m["url"] = PAGE.format(t=m["appl_type"], n=m["appl_no"])
        m["date"], m["source"] = m["expires"], SOURCE
    return sorted(merged.values(), key=lambda x: (x["expires"] or "9999", x["application"], x["kind"], x["code"]))


def _match(v: str | None, terms) -> bool:
    return any(filters._hit((v or "").lower(), t) for t in terms)


def protections(client, company=None, ingredient=None, trade_name=None, application: str | None = None, kind=None,
                since: str | None = None, until: str | None = None, upcoming_days: int | None = None,
                include_expired: bool = False, include_delisted: bool = True, keyword: str | None = None,
                exclude=None, max_records: int = 100, today_: str | None = None) -> list[dict]:
    """Patent and exclusivity listings, soonest expiry first. since/until filter the expiry date; upcoming_days keeps
    listings expiring within that many days of today. Expired listings are dropped unless include_expired."""
    kinds = [kind] if isinstance(kind, str) else list(kind or [])
    bad = [k for k in kinds if k not in KINDS]
    if bad: raise ValueError(f"kind must be among {', '.join(KINDS)}")
    t0 = today_ or date.today().isoformat()
    lo = since if since else (None if include_expired else t0)
    hi = until
    if upcoming_days is not None:
        h = (date.fromisoformat(t0) + timedelta(days=int(upcoming_days))).isoformat()
        hi = min(hi, h) if hi else h
        lo = max(lo, t0) if lo else t0
    app = parse_application(application) if application else None
    L = lambda x: [x] if isinstance(x, str) else list(x or [])
    out = []
    for r in listings(client.tables()):
        if kinds and r["kind"] not in kinds: continue
        if app and (r["appl_no"] != app[1] or (app[0] and r["appl_type"] != app[0])): continue
        if lo and (not r["expires"] or r["expires"] < lo): continue
        if hi and (not r["expires"] or r["expires"] > hi): continue
        if not include_delisted and r.get("delisted"): continue
        if company and not _match(r["applicant"], L(company)): continue
        if ingredient and not _match(r["ingredient"], L(ingredient)): continue
        if trade_name and not _match(r["trade_name"], L(trade_name)): continue
        if keyword and not _match(" ".join(str(r[f] or "") for f in ("trade_name", "ingredient", "applicant", "code")), [keyword]): continue
        out.append(r)
    out = filters.exclude(out, exclude, fields=("trade_name", "ingredient", "applicant"))
    return out[:max_records]


def loe(client, max_records: int = 100, **kw) -> list[dict]:
    """Per application: the last listed protection (latest unexpired patent or exclusivity expiry), soonest first.
    This is the earliest date generic/505(b)(2) competition is not blocked by any *listed* protection; real entry can
    differ (settlements, litigation, unlisted patents, 30-month stays)."""
    rows = protections(client, max_records=10**7, **kw)
    by: dict = {}
    for r in rows:
        a = by.setdefault(r["application"], {"key": f"loe:{r['appl_type']}{r['appl_no']}", "application": r["application"],
                                             "trade_name": r["trade_name"], "ingredient": r["ingredient"], "applicant": r["applicant"],
                                             "last_protection": None, "last_protection_code": None, "patents": 0, "exclusivities": 0,
                                             "url": r["url"], "source": SOURCE})
        a["patents" if r["kind"] == "patent" else "exclusivities"] += 1
        if r["expires"] and (a["last_protection"] is None or r["expires"] > a["last_protection"]):
            a["last_protection"], a["last_protection_code"] = r["expires"], f"{r['kind']} {r['code']}"
    out = sorted(by.values(), key=lambda x: (x["last_protection"] or "9999", x["application"]))
    for a in out:
        a["date"] = a["last_protection"]
        a["title"] = f"{a['trade_name'] or a['ingredient']} ({a['application']}) last listed protection {a['last_protection']} ({a['last_protection_code']})"
    return out[:max_records]


def store(path: str) -> ItemStore:
    return ItemStore(path, "ob", TRACKED, new_kind="new_listing")


def run_watch(client, st: ItemStore, watch: str, **kw) -> dict:
    kw.setdefault("max_records", 100000)
    kw.setdefault("include_expired", True)  # so an expiry moving earlier/later is seen as a change, not a disappearance
    rows = protections(client, **kw)
    info = st.ingest(watch, rows, query=kw)
    info["changes_detail"] = st.changes(watch=watch, run_id=info["run_id"])
    return info
