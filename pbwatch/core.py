"""FDA Purple Book: licensed biological products (BLAs), biosimilars / interchangeables, reference-product exclusivity.

Source: U.S. Food and Drug Administration, "Purple Book: Database of Licensed Biological Products", monthly data
download (CSV) listed on https://purplebooksearch.fda.gov/index.cfm?event=downloads (e.g.
https://www.accessdata.fda.gov/drugsatfda_docs/PurpleBook/2026/purplebook-search-October-data-download.csv; the month's
casing varies between years, so the newest link is read from the downloads page, never guessed first). U.S. government
work, public domain (FDA website policies). Each monthly file has two sections with the same 28 columns: the month's
changes (N = newly approved, R = added in this release, U = updated) and then every product in the database.

FDA lists reference-product, first-interchangeable and orphan exclusivity only where it has made a determination, so a
blank date does not mean "no exclusivity". Patents are not listed (only a 'patent list provided' flag); biosimilar
launch timing also depends on BPCIA patent litigation and settlements. The CSV is cached locally (default 24 h).
"""
from __future__ import annotations
import csv, io, json, os, re, time, urllib.error, urllib.request
from datetime import date, datetime, timedelta
from biowatch import filters
from biowatch.store import ItemStore

DOWNLOADS = "https://purplebooksearch.fda.gov/index.cfm?event=downloads"
FILE_URL = "https://www.accessdata.fda.gov/drugsatfda_docs/PurpleBook/{y}/purplebook-search-{m}-data-download.csv"
PAGE = "https://purplebooksearch.fda.gov/index.cfm?blaNo={n}&event=productdetails"
SOURCE = "U.S. Food and Drug Administration, Purple Book database of licensed biological products (purplebooksearch.fda.gov); public domain"
UA = "BioCatalystFeed (https://github.com/biocatalystfeed/biocatalystfeed; contact@biocat.ai)"
LINK_RE = re.compile(r"https://www\.accessdata\.fda\.gov/drugsatfda_docs/PurpleBook/(\d{4})/purplebook-search-([A-Za-z]+)-data-download\.csv")
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
TYPES = ("351(a)", "biosimilar", "interchangeable")
EXCL_KINDS = ("reference", "first_interchangeable", "orphan")
TRACKED = ("licensure", "license_types", "interchangeable_approved", "ref_exclusivity_expires",
           "interchangeable_exclusivity_expires", "orphan_exclusivity_expires", "products", "marketing_status",
           "applicant", "reference_product")
BLA_RE = re.compile(r"^(?:BLA\s*)?(\d{1,6})$", re.I)
COLS = {"flag": "N/R/U", "applicant": "Applicant", "bla": "BLA Number", "proprietary": "Proprietary Name",
        "proper": "Proper Name", "type": "License Type", "strength": "Strength", "form": "Dosage Form",
        "route": "Route of Administration", "presentation": "Product Presentation", "marketing": "Marketing Status",
        "licensure": "Licensure", "approved": "Approval Date", "inter_approved": "Inter. Approval Date",
        "ref_proper": "Ref. Product Proper Name", "ref_proprietary": "Ref. Product Proprietary Name",
        "submission": "Submission Type", "license_no": "License Number", "product_no": "Product Number", "center": "Center",
        "first_licensure": "Date of First Licensure", "excl": "Exclusivity Expiration Date",
        "inter_excl": "First Interchangeable Exclusivity Exp. Date", "ref_excl": "Ref. Product Exclusivity Exp. Date",
        "orphan_excl": "Orphan Exclusivity Exp. Date", "patents": "Patent List Provided"}


def latest_link(html: str) -> tuple[str, str] | None:
    """Newest CSV link on the downloads page -> (url, 'October 2026'), by (year, month) not page order."""
    best = None
    for m in LINK_RE.finditer(html or ""):
        mon = m.group(2).lower()
        if mon not in MONTHS: continue
        k = (int(m.group(1)), MONTHS.index(mon))
        if best is None or k > best[0]: best = (k, m.group(0))
    return None if best is None else (best[1], f"{MONTHS[best[0][1]].title()} {best[0][0]}")


def _decode(data: bytes) -> str:
    try: return data.decode("utf-8-sig")
    except UnicodeDecodeError: return data.decode("latin-1")


class PurpleBookClient:
    """Finds the newest monthly CSV on the Purple Book downloads page, downloads it with a descriptive User-Agent and
    caches it (default 24 h). `tables()` returns {'report', 'url', 'changes': [...], 'products': [...]}."""

    def __init__(self, cache_dir: str | None = None, max_age_hours: float = 24, downloads: str = DOWNLOADS, timeout: int = 120):
        d = cache_dir or os.path.expanduser("~/.cache/biocatalystfeed")
        self.cache, self.meta = os.path.join(d, "purplebook.csv"), os.path.join(d, "purplebook.json")
        self.max_age, self.downloads, self.timeout = max_age_hours * 3600, downloads, timeout
        self._tables, self.retry_pause = None, 2.0

    def _get(self, url: str, retries: int = 1) -> bytes:
        """GET with a descriptive User-Agent. FDA's edge occasionally answers 401/403/429/5xx to a first request; retry
        once after a short pause, then give up (never with a browser User-Agent)."""
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r: return r.read()
        except urllib.error.HTTPError as e:
            if retries <= 0 or not (e.code in (401, 403, 429) or e.code >= 500): raise
            time.sleep(self.retry_pause)
            return self._get(url, retries - 1)

    def discover(self) -> list[str]:
        """Candidate CSV URLs, best first: the newest link on the downloads page, else this and the previous two months
        in both casings FDA has used (e.g. 'October' and 'october')."""
        try:
            hit = latest_link(_decode(self._get(self.downloads)))
            if hit: return [hit[0]]
        except Exception:  # page down or challenged: fall back to the documented file pattern
            pass
        out, d = [], date.today().replace(day=1)
        for _ in range(3):
            m = MONTHS[d.month - 1]
            out += [FILE_URL.format(y=d.year, m=m.title()), FILE_URL.format(y=d.year, m=m)]
            d = (d - timedelta(days=1)).replace(day=1)
        return out

    def fetch(self) -> tuple[bytes, str]:
        if os.path.exists(self.cache) and time.time() - os.path.getmtime(self.cache) < self.max_age:
            url = None
            if os.path.exists(self.meta):
                with open(self.meta) as f: url = json.load(f).get("url")
            with open(self.cache, "rb") as f: return f.read(), url
        err = None
        for url in self.discover():
            try: data = self._get(url)
            except Exception as e: err = e; continue
            if not looks_like_purple_book(data):
                err = RuntimeError("Purple Book download did not return the expected CSV"); continue
            os.makedirs(os.path.dirname(self.cache), exist_ok=True)
            with open(self.cache + ".tmp", "wb") as f: f.write(data)
            os.replace(self.cache + ".tmp", self.cache)
            with open(self.meta, "w") as f: json.dump({"url": url, "fetched": datetime.now().isoformat(timespec="seconds")}, f)
            return data, url
        raise RuntimeError(f"could not download the Purple Book CSV ({err})")

    def tables(self) -> dict:
        if self._tables is None:
            data, url = self.fetch()
            self._tables = parse_csv(_decode(data)); self._tables["url"] = url
        return self._tables


def looks_like_purple_book(data: bytes) -> bool:
    head = _decode(data[:4000]).lstrip()
    return head.startswith("Purple Book") or ("BLA Number" in head and "License Type" in head)


def parse_csv(text: str) -> dict:
    """Split the monthly file into its 'changes' (rows flagged N/R/U) and full 'products' sections."""
    rows = list(csv.reader(io.StringIO(text)))
    first = (rows[0][0] if rows and rows[0] else "").strip()
    m = re.search(r"-\s*([A-Za-z]+ \d{4})\s*$", first)
    heads = [i for i, r in enumerate(rows) if r and r[0].strip() == COLS["flag"] and COLS["bla"] in r]
    if not heads: raise RuntimeError("Purple Book CSV has no header row (format changed?)")
    missing = [v for v in COLS.values() if v not in rows[heads[0]]]
    if missing: raise RuntimeError(f"Purple Book CSV is missing columns: {', '.join(missing)}")

    def section(h, end):
        names = [c.strip() for c in rows[h]]
        out = []
        for r in rows[h + 1:end]:
            if not any(c.strip() for c in r): continue
            d = dict(zip(names, (c.strip() for c in r)))
            if d.get(COLS["bla"]): out.append(d)
        return out
    changes = section(heads[0], heads[1]) if len(heads) > 1 else []
    products = section(heads[-1], len(rows))
    return {"report": m.group(1) if m else None, "changes": changes, "products": products}


def iso(d: str | None) -> str | None:
    """'October 22, 2026' -> '2026-10-22'; blank or 'Not Eligible' -> None."""
    try: return datetime.strptime((d or "").strip(), "%B %d, %Y").date().isoformat()
    except ValueError: return None


def parse_bla(a: str) -> str:
    m = BLA_RE.match((a or "").strip())
    if not m: raise ValueError("application must look like 'BLA 761378' or '761378'")
    return m.group(1).zfill(6)


def _uniq(xs) -> list[str]:
    return list(dict.fromkeys(x for x in xs if x and x.strip() and x.strip().upper() != "N/A"))


def _min(xs):
    xs = [x for x in xs if x]
    return min(xs) if xs else None


def _max(xs):
    xs = [x for x in xs if x]
    return max(xs) if xs else None


def licenses(tables: dict) -> list[dict]:
    """One record per BLA (license), merged over its product numbers, newest original approval first."""
    flags: dict = {}
    for r in tables.get("changes", []):
        f = r.get(COLS["flag"])
        if f: flags.setdefault(r[COLS["bla"]], set()).add(f)
    by: dict = {}
    for r in tables["products"]:
        by.setdefault(r[COLS["bla"]], []).append(r)
    out = []
    for n, ps in by.items():
        g = lambda k: [p.get(COLS[k], "") for p in ps]
        types = sorted(set(t for t in g("type") if t))
        lic = [p for p in ps if p.get(COLS["licensure"]) == "Licensed"]
        statuses = sorted(set(s for s in g("licensure") if s))
        biosimilar = any(t.startswith("351(k)") for t in types)
        rec = {"key": f"pb:{n}", "bla": f"BLA {n}", "bla_no": n, "applicant": (_uniq(g("applicant")) or [None])[0],
               "proprietary_name": "; ".join(_uniq(g("proprietary"))) or None, "proper_name": "; ".join(_uniq(g("proper"))) or None,
               "license_types": types, "pathway": "351(k)" if biosimilar else "351(a)", "biosimilar": biosimilar,
               "interchangeable": "351(k) Interchangeable" in types,
               "approved": _min(iso(x) for x in g("approved")),
               "latest_product_approved": _max(iso(x) for x in g("approved")),
               "interchangeable_approved": _min(iso(x) for x in g("inter_approved")),
               "reference_product": "; ".join(_uniq(g("ref_proprietary"))) or None,
               "reference_proper_name": "; ".join(_uniq(g("ref_proper"))) or None,
               "licensure": "Licensed" if lic else ("; ".join(statuses) or None),
               "products": sorted(p.get(COLS["product_no"]) for p in lic),
               "revoked_products": len(ps) - len(lic),
               "marketing_status": sorted(set(s for s in (p.get(COLS["marketing"]) for p in lic) if s)),
               "center": (_uniq(g("center")) or [None])[0], "license_number": (_uniq(g("license_no")) or [None])[0],
               "first_licensure": _min(iso(x) for x in g("first_licensure")),
               "ref_exclusivity_expires": _max(iso(x) for x in g("ref_excl")),
               "interchangeable_exclusivity_expires": _max(iso(x) for x in g("inter_excl")),
               "orphan_exclusivity_expires": _max(iso(x) for x in g("orphan_excl")),
               "exclusivity_expires": _max(iso(x) for x in g("excl")),
               "patent_list_provided": any(x.upper() == "YES" for x in g("patents")),
               "monthly_flags": sorted(flags.get(n, ())), "report": tables.get("report"),
               "url": PAGE.format(n=n), "source": SOURCE}
        kind = "interchangeable" if rec["interchangeable"] else "biosimilar" if biosimilar else "351(a)"
        name = rec["proprietary_name"] or rec["proper_name"]
        ref = f" to {rec['reference_product']}" if biosimilar and rec["reference_product"] else ""
        rec["title"] = f"{name} ({rec['proper_name']}, {rec['bla']}) {kind}{ref}, {rec['applicant']}, approved {rec['approved'] or '?'}"
        if rec["licensure"] != "Licensed": rec["title"] += f" [{rec['licensure']}]"
        rec["date"] = rec["approved"]
        out.append(rec)
    return sorted(out, key=lambda x: (x["approved"] or "0000", x["bla_no"]), reverse=True)


def _match(v, terms) -> bool:
    return any(filters._hit((v or "").lower(), t) for t in terms)


def _L(x):
    return [x] if isinstance(x, str) else list(x or [])


def products(client, company=None, name=None, reference=None, license_type=None, application: str | None = None,
             center: str | None = None, since: str | None = None, until: str | None = None, recent_days: int | None = None,
             monthly_changes: bool = False, include_revoked: bool = False, keyword: str | None = None, exclude=None,
             max_records: int = 100, today_: str | None = None) -> list[dict]:
    """Licensed biologics (one row per BLA), newest original approval first. license_type: any of '351(a)',
    'biosimilar' (all 351(k), incl. interchangeables), 'interchangeable'. since/until/recent_days filter the BLA's
    original approval date; monthly_changes keeps BLAs FDA flagged N/R/U in the current monthly report."""
    types = _L(license_type)
    bad = [t for t in types if t not in TYPES]
    if bad: raise ValueError(f"license_type must be among {', '.join(TYPES)}")
    bla = parse_bla(application) if application else None
    lo, hi = since, until
    if recent_days is not None:
        lo = (date.fromisoformat(today_ or date.today().isoformat()) - timedelta(days=int(recent_days))).isoformat()
    out = []
    for r in licenses(client.tables()):
        if not include_revoked and r["licensure"] != "Licensed": continue
        if bla and r["bla_no"] != bla: continue
        if types and not any(t == "351(a)" and not r["biosimilar"] or t == "biosimilar" and r["biosimilar"]
                             or t == "interchangeable" and r["interchangeable"] for t in types): continue
        if center and (r["center"] or "").upper() != center.upper(): continue
        if lo and (not r["approved"] or r["approved"] < lo): continue
        if hi and (not r["approved"] or r["approved"] > hi): continue
        if monthly_changes and not r["monthly_flags"]: continue
        if company and not _match(r["applicant"], _L(company)): continue
        if name and not _match(f"{r['proprietary_name'] or ''} {r['proper_name'] or ''}", _L(name)): continue
        if reference and not _match(f"{r['reference_product'] or ''} {r['reference_proper_name'] or ''}", _L(reference)): continue
        if keyword and not _match(" ".join(str(r[f] or "") for f in ("proprietary_name", "proper_name", "applicant", "reference_product")), [keyword]): continue
        out.append(r)
    out = filters.exclude(out, exclude, fields=("proprietary_name", "proper_name", "applicant", "reference_product"))
    return out[:max_records]


def exclusivities(client, company=None, name=None, kind=None, since: str | None = None, until: str | None = None,
                  upcoming_days: int | None = None, include_expired: bool = False, keyword: str | None = None,
                  exclude=None, max_records: int = 100, today_: str | None = None) -> list[dict]:
    """Biologic exclusivity expiries FDA lists, soonest first: 'reference' (12-year reference product exclusivity),
    'first_interchangeable' and 'orphan'. Expired ones are dropped unless include_expired."""
    kinds = _L(kind)
    bad = [k for k in kinds if k not in EXCL_KINDS]
    if bad: raise ValueError(f"kind must be among {', '.join(EXCL_KINDS)}")
    t0 = today_ or date.today().isoformat()
    lo = since if since else (None if include_expired else t0)
    hi = until
    if upcoming_days is not None:
        h = (date.fromisoformat(t0) + timedelta(days=int(upcoming_days))).isoformat()
        hi = min(hi, h) if hi else h
        lo = max(lo, t0) if lo else t0
    field = {"reference": "ref_exclusivity_expires", "first_interchangeable": "interchangeable_exclusivity_expires",
             "orphan": "orphan_exclusivity_expires"}
    out = []
    for r in products(client, company=company, name=name, keyword=keyword, include_revoked=True, max_records=10**7):
        for k, f in field.items():
            exp = r[f]
            if not exp or (kinds and k not in kinds): continue
            if lo and exp < lo or hi and exp > hi: continue
            out.append({"key": f"pbx:{r['bla_no']}:{k}", "kind": k, "expires": exp, "bla": r["bla"],
                        "proprietary_name": r["proprietary_name"], "proper_name": r["proper_name"], "applicant": r["applicant"],
                        "license_types": r["license_types"], "reference_product": r["reference_product"],
                        "licensure": r["licensure"], "url": r["url"], "source": SOURCE, "date": exp,
                        "title": f"{r['proprietary_name'] or r['proper_name']} ({r['bla']}) {k.replace('_', '-')} exclusivity expires {exp}"})
    out = filters.exclude(out, exclude, fields=("proprietary_name", "proper_name", "applicant", "reference_product"))
    return sorted(out, key=lambda x: (x["expires"], x["bla"], x["kind"]))[:max_records]


def _core(n: str | None) -> str:
    """'adalimumab-aaty' / 'Adalimumab' -> 'adalimumab' (FDA's four-letter suffix dropped)."""
    n = (n or "").strip().lower()
    return re.sub(r"-[a-z]{4}$", "", n)


def landscape(client, reference=None, company=None, keyword: str | None = None, include_unchallenged: bool = False,
              max_records: int = 100, today_: str | None = None) -> list[dict]:
    """Biologic loss-of-exclusivity view: one row per reference product with its 351(a) BLA(s), FDA-listed reference
    product exclusivity expiry, and every licensed biosimilar / interchangeable (count, first and latest approval,
    first-interchangeable exclusivity). include_unchallenged adds reference products with a listed exclusivity date
    and no biosimilar yet. Most biosimilar-heavy first. Launch timing also depends on patents and settlements."""
    t0 = today_ or date.today().isoformat()
    rows = products(client, max_records=10**7)
    orig: dict = {}
    for r in rows:
        if not r["biosimilar"]: orig.setdefault(_core(r["proper_name"]), []).append(r)
    groups: dict = {}
    for r in rows:
        if not r["biosimilar"]: continue
        k = _core(r["reference_proper_name"] or r["proper_name"])
        groups.setdefault(k, []).append(r)
    split = lambda xs: _uniq(p.strip() for x in xs for p in (x or "").split(";"))
    todo = []
    for k, bs in groups.items():
        names = split(b["reference_product"] for b in bs)
        refs = orig.get(k, [])
        named = [o for o in refs if set(n.lower() for n in split([o["proprietary_name"]])) & set(n.lower() for n in names)]
        todo.append((k, named or refs, bs, names))
    if include_unchallenged:  # one row per 351(a) BLA with a listed reference exclusivity and no biosimilar yet
        for k, os_ in orig.items():
            if k in groups: continue
            todo += [(k, [o], [], split([o["proprietary_name"]])) for o in os_ if o["ref_exclusivity_expires"]]
    out = []
    for k, refs, bs, names in todo:
        ref_name = "; ".join(names) or None
        if reference and not _match(f"{ref_name or ''} {k}", _L(reference)): continue
        if company and not _match(" ".join(x["applicant"] or "" for x in refs + bs), _L(company)): continue
        if keyword and not _match(" ".join(f"{x['proprietary_name']} {x['proper_name']} {x['applicant']}" for x in refs + bs) + f" {ref_name} {k}", [keyword]): continue
        rex = _max(o["ref_exclusivity_expires"] for o in refs)
        bs = sorted(bs, key=lambda b: (b["approved"] or "", b["bla_no"]))
        a = {"key": f"pbl:{k}" + ("" if bs else f":{refs[0]['bla_no']}"), "reference_product": ref_name, "reference_proper_name": k,
             "reference_blas": [o["bla"] for o in refs], "reference_applicant": "; ".join(_uniq([o["applicant"] or "" for o in refs])) or None,
             "reference_exclusivity_expires": rex, "reference_exclusivity_expired": bool(rex and rex < t0),
             "biosimilars": len(bs), "interchangeables": sum(b["interchangeable"] for b in bs),
             "first_biosimilar_approved": bs[0]["approved"] if bs else None, "latest_biosimilar_approved": bs[-1]["approved"] if bs else None,
             "products": [{"bla": b["bla"], "name": b["proprietary_name"], "proper_name": b["proper_name"], "applicant": b["applicant"],
                           "approved": b["approved"], "interchangeable": b["interchangeable"],
                           "interchangeable_approved": b["interchangeable_approved"],
                           "first_interchangeable_exclusivity_expires": b["interchangeable_exclusivity_expires"], "url": b["url"]} for b in bs],
             "url": refs[0]["url"] if refs else (bs[0]["url"] if bs else None), "source": SOURCE}
        a["date"] = a["latest_biosimilar_approved"] or rex
        a["title"] = (f"{ref_name or k}: {a['biosimilars']} biosimilar(s), {a['interchangeables']} interchangeable"
                      + (f"; reference exclusivity {rex}" if rex else ""))
        out.append(a)
    out.sort(key=lambda x: (-x["biosimilars"], x["reference_exclusivity_expires"] or "9999", x["reference_proper_name"]))
    return out[:max_records]


def store(path: str) -> ItemStore:
    return ItemStore(path, "pb", TRACKED, new_kind="new_bla")


def run_watch(client, st: ItemStore, watch: str, **kw) -> dict:
    kw.setdefault("max_records", 100000)
    kw.setdefault("include_revoked", True)  # so a revocation is seen as licensure_change, not a disappearance
    rows = products(client, **kw)
    info = st.ingest(watch, rows, query=kw)
    info["changes_detail"] = st.changes(watch=watch, run_id=info["run_id"])
    return info
