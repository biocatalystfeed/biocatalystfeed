"""NIH RePORTER API v2 (https://api.reporter.nih.gov). Public, no key. Policy: <=1 request/second; large jobs on
weekends or weekdays 9 PM-5 AM ET; limit<=500 per page, offset<=14,999. We throttle to 1 req/s."""
from __future__ import annotations
import re
from datetime import date
from biowatch.http import Throttled
from biowatch.store import ItemStore

URL = "https://api.reporter.nih.gov/v2/projects/search"
TRACKED = ("award_amount", "project_end_date", "award_notice_date", "fiscal_year", "org_name", "pis")


class ReporterClient(Throttled):
    def __init__(self, **kw):
        super().__init__(min_interval=kw.pop("min_interval", 1.0), **kw)

    def search(self, criteria: dict, max_records: int = 500, sort_field: str = "award_notice_date") -> list[dict]:
        out, offset = [], 0
        while len(out) < max_records and offset <= 14999:
            d = self.post_json(URL, {"criteria": criteria, "offset": offset, "limit": min(500, max_records - len(out)),
                                     "sort_field": sort_field, "sort_order": "desc"})
            res = d.get("results") or []
            out += res; offset += len(res)
            if not res or offset >= d.get("meta", {}).get("total", 0): break
        return out


def build_criteria(org: list[str] | str | None = None, pi: str | None = None, keyword: str | None = None,
                   since: str | None = None, until: str | None = None, fiscal_years: list[int] | None = None,
                   org_exact: bool = False) -> dict:
    c: dict = {}
    if org:
        c["org_names_exact_match" if org_exact else "org_names"] = [org] if isinstance(org, str) else list(org)
    if pi:
        n = parse_name(pi)
        c["pi_names"] = [{"first_name": n["first"], "last_name": n["last"]} if n["first"] else {"any_name": pi}]
    if keyword:  # 'a OR b' -> RePORTER "or" operator (any term); otherwise all terms must match
        op = "or" if " OR " in keyword else "and"
        c["advanced_text_search"] = {"operator": op, "search_field": "projecttitle,terms,abstracttext", "search_text": keyword.replace(" OR ", " ")}
    if since or until: c["award_notice_date"] = {"from_date": since or "", "to_date": until or ""}
    if fiscal_years: c["fiscal_years"] = fiscal_years
    if not c: raise ValueError("give at least one of org / pi / keyword / since / fiscal_years")
    return c


def parse_name(s: str) -> dict:
    """'Jane A. Doe' / 'Doe, Jane A' / 'DOE, JANE ALICE' -> {'first','middle','last'} (lowercase; middle may be '')."""
    s = re.sub(r"\s+", " ", (s or "").replace(".", " ")).strip().lower()
    if "," in s:
        last, rest = [x.strip() for x in s.split(",", 1)]
        toks = rest.split()
    else:
        toks = s.split()
        if len(toks) < 2: return {"first": "", "middle": "", "last": s}
        last, toks = toks[-1], toks[:-1]
    return {"first": toks[0] if toks else "", "middle": " ".join(toks[1:]), "last": last}


def pi_matches(pi: dict, query: str, exact: bool = False) -> bool:
    """Does a RePORTER PI record ({first_name, middle_name, last_name, full_name}) match the query name?
    Last name must match exactly. First name must match exactly (a one-letter query first name matches as an initial).
    If the query gives a middle name/initial and the PI record has one, their initials must agree. exact=True also
    requires the PI to have the same middle initial (no blank middles) and, for full middle names, the same name."""
    q = parse_name(query)
    rec = {"first": (pi.get("first_name") or "").lower().replace(".", "").strip(),
           "middle": (pi.get("middle_name") or "").lower().replace(".", "").strip(),
           "last": (pi.get("last_name") or "").lower().strip()}
    if not rec["last"] and pi.get("full_name"): rec = parse_name(pi["full_name"])
    if rec["last"] != q["last"]: return False
    if not q["first"]: return True
    f = rec["first"].split()[0] if rec["first"] else ""
    if len(q["first"]) == 1 and not exact:
        if not f.startswith(q["first"]): return False
    elif f != q["first"]: return False
    if q["middle"]:
        if not rec["middle"]: return not exact
        if rec["middle"][0] != q["middle"][0]: return False
        if exact and len(q["middle"]) > 1 and len(rec["middle"]) > 1 and rec["middle"] != q["middle"]: return False
    elif exact and rec["middle"]:
        return False
    return True


def sort_grants(rows: list[dict], today: str | None = None, include_future: bool = True, by: str = "award_notice_date") -> list[dict]:
    """Newest award notice first. Records dated after `today` (e.g. next-FY awards pre-loaded by NIH) are flagged
    future_dated and placed after current ones so they don't crowd the top; include_future=False drops them."""
    today = today or date.today().isoformat()
    for r in rows: r["future_dated"] = (r.get("award_notice_date") or "") > today
    if not include_future: rows = [r for r in rows if not r["future_dated"]]
    if by == "award_notice_date":
        return sorted(rows, key=lambda r: (not r["future_dated"], r.get("award_notice_date") or ""), reverse=True)
    if by == "relevance":
        return sorted(rows, key=lambda r: (r.get("relevance") or 0, not r["future_dated"], r.get("award_notice_date") or ""), reverse=True)
    return sorted(rows, key=lambda r: (r.get(by) or 0, r.get("award_notice_date") or ""), reverse=True)


def normalize(p: dict) -> dict:
    org = p.get("organization") or {}
    pis = "; ".join(x.get("full_name", "").strip() for x in p.get("principal_investigators") or [])
    ic = (p.get("agency_ic_admin") or {}).get("abbreviation")
    return {"key": str(p.get("appl_id")), "appl_id": p.get("appl_id"), "project_num": p.get("project_num"),
            "core_project_num": p.get("core_project_num"), "fiscal_year": p.get("fiscal_year"),
            "title": p.get("project_title"), "org_name": org.get("org_name"), "org_state": org.get("org_state"),
            "pis": pis, "agency": ic, "activity_code": p.get("activity_code"), "award_type": p.get("award_type"),
            "award_amount": p.get("award_amount"), "award_notice_date": (p.get("award_notice_date") or "")[:10] or None,
            "project_start_date": (p.get("project_start_date") or "")[:10] or None,
            "project_end_date": (p.get("project_end_date") or "")[:10] or None,
            "pi_list": [{k: x.get(k) for k in ("first_name", "middle_name", "last_name", "full_name")} for x in p.get("principal_investigators") or []],
            "is_active": p.get("is_active"), "url": p.get("project_detail_url") or f"https://reporter.nih.gov/project-details/{p.get('appl_id')}"}


def search_grants(client: ReporterClient, max_records: int = 200, pi_exact: bool = False, exclude=None, rank: bool = False,
                  include_future: bool = True, sort: str = "award_notice_date", today: str | None = None, **kw) -> list[dict]:
    """kw -> build_criteria. PI results are post-filtered with pi_matches (RePORTER's own PI search ignores middle names).
    exclude drops grants mentioning any term; rank/sort='relevance' orders by query-term relevance."""
    from biowatch import filters
    rows = [normalize(p) for p in client.search(build_criteria(**kw), max_records=max_records)]
    if kw.get("pi") and parse_name(kw["pi"])["first"]:
        rows = [r for r in rows if any(pi_matches(x, kw["pi"], pi_exact) for x in r["pi_list"])
                or (not r["pi_list"] and pi_matches({"full_name": r["pis"]}, kw["pi"], pi_exact))]
    rows = filters.exclude(rows, exclude)
    if rank or sort == "relevance":
        terms = filters.query_terms(kw.get("keyword"), kw.get("org"))
        for r in rows: r["relevance"] = filters.score(r, terms)
        sort = "relevance"
    return sort_grants(rows, today=today, include_future=include_future, by=sort)


def company_grants(client: ReporterClient, alias: dict, max_records: int = 200) -> list[dict]:
    """Grants to a company's organisation names (alias field nih_orgs, exact match). Empty list if none configured."""
    orgs = alias.get("nih_orgs")
    if not orgs: return []
    return search_grants(client, org=orgs, org_exact=True, max_records=max_records)


def store(path: str) -> ItemStore:
    return ItemStore(path, "grant", TRACKED, new_kind="new_award")


def run_watch(client: ReporterClient, st: ItemStore, watch: str, max_records: int = 500, **kw) -> dict:
    rows = search_grants(client, max_records=max_records, **kw)
    for r in rows: r.pop("relevance", None); r.pop("future_dated", None)  # derived fields, not tracked
    info = st.ingest(watch, rows, query=kw)
    info["changes_detail"] = st.changes(watch=watch, run_id=info["run_id"])
    return info
