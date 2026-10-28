"""Market-wide trial readout calendar from ClinicalTrials.gov (API v2, public, no key).

A "readout" here is a trial's PRIMARY COMPLETION DATE: the date the sponsor says the last participant is examined for
the primary outcome. Top-line data usually follow weeks to months later; sponsors often slip these dates.
readout_date_type is ESTIMATED (sponsor's anticipated date) or ACTUAL. This is scheduling/reference data, not a
prediction of when results are announced and not investment advice.

Filters: sponsor (name or ticker; alias-resolved, unknown US tickers looked up in SEC's ticker list), condition,
intervention, phases, since/until or upcoming_days, statuses, industry_only (default true: LeadSponsorClass INDUSTRY),
ticker_only (keep only trials whose sponsor matched a ticker). Every record carries verified_as_of, verify_hash,
source_url (the CT.gov API record) and ticker / ticker_confidence / ticker_method (see biowatch.provenance).
Watching: snapshots go to the local DB (prefix `readout`); a later run reports new_readout, readout_date_change (date
slipped or pulled in), readout_date_type_change (ESTIMATED -> ACTUAL), status_change, enrollment_change, phase_change."""
from __future__ import annotations
from datetime import date, timedelta
from biowatch import provenance as pv
from biowatch.store import ItemStore
from trialwatch.client import CTGovClient, FIELDS, PHASES, STATUSES
from trialwatch.normalize import normalize

SOURCE = "ClinicalTrials.gov API v2 (U.S. National Library of Medicine; public data)"
API = "https://clinicaltrials.gov/api/v2/studies"
ACTIVE = ("NOT_YET_RECRUITING", "RECRUITING", "ENROLLING_BY_INVITATION", "ACTIVE_NOT_RECRUITING")
TRACKED = ("readout_date", "readout_date_type", "status", "enrollment", "phase")
DEFAULT_PHASES = ("PHASE2", "PHASE3")


def today_iso() -> str:
    return date.today().isoformat()


def _window(since, until, upcoming_days, today):
    if upcoming_days is not None or not (since or until):
        n = 90 if upcoming_days is None else int(upcoming_days)
        return today, (date.fromisoformat(today) + timedelta(days=n)).isoformat()
    return since or today, until or (date.fromisoformat(since or today) + timedelta(days=365)).isoformat()


def params(sponsor=None, condition=None, intervention=None, phases=DEFAULT_PHASES, statuses=ACTIVE, since=None, until=None,
           industry_only=True, date_field="PrimaryCompletionDate", extra_adv=None) -> dict:
    """CT.gov v2 /studies query params, sorted by primary completion date ascending."""
    p = {"fields": FIELDS, "format": "json", "sort": f"{date_field}:asc"}
    if sponsor: p["query.spons"] = sponsor
    if condition: p["query.cond"] = condition
    if intervention: p["query.intr"] = intervention
    if statuses:
        bad = {s.upper() for s in statuses} - STATUSES
        if bad: raise ValueError(f"unknown status {bad}")
        p["filter.overallStatus"] = ",".join(s.upper() for s in statuses)
    adv = [f"AREA[{date_field}]RANGE[{since or 'MIN'},{until or 'MAX'}]"]
    if phases:
        bad = {x.upper() for x in phases} - PHASES
        if bad: raise ValueError(f"unknown phase {bad}; use {sorted(PHASES)}")
        adv.append("(" + " OR ".join(f"AREA[Phase]{x.upper()}" for x in phases) + ")")
    if industry_only: adv.append("AREA[LeadSponsorClass]INDUSTRY")
    adv += list(extra_adv or [])
    p["filter.advanced"] = " AND ".join(adv)
    return p


def fetch(client: CTGovClient, p: dict, max_records: int) -> list[dict]:
    p = dict(p, pageSize=min(1000, max_records))
    out: list[dict] = []
    while True:
        data = client._get("/studies", p)
        out += data.get("studies", [])
        tok = data.get("nextPageToken")
        if not tok or len(out) >= max_records: return out[:max_records]
        p["pageToken"] = tok


def to_event(t: dict, as_of: str, today: str) -> dict:
    d = t.get("primary_completion_date")
    tm = pv.ticker_match(t.get("lead_sponsor"))
    ev = {"key": f"readout:{t['nct_id']}", "kind": "readout", "nct_id": t["nct_id"], "title": t.get("title"),
          "acronym": t.get("acronym"), "readout_date": d, "date_precision": "day" if d and len(d) == 10 else ("month" if d else None),
          "readout_date_type": t.get("primary_completion_type"), "completion_date": t.get("completion_date"),
          "status": t.get("status"), "phase": t.get("phase"), "sponsor": t.get("lead_sponsor"), "sponsor_class": t.get("sponsor_class"),
          "conditions": t.get("conditions"), "interventions": t.get("interventions"), "enrollment": t.get("enrollment"),
          "enrollment_type": t.get("enrollment_type"), "primary_outcomes": (t.get("primary_outcomes") or "")[:400] or None,
          "last_update_posted": t.get("last_update_posted"), "why_stopped": t.get("why_stopped"),
          "overdue": bool(d and d < today[:len(d)] and t.get("primary_completion_type") != "ACTUAL"),
          "url": t.get("url"), **tm,
          "provenance": {"source": SOURCE, "field": "protocolSection.statusModule.primaryCompletionDateStruct", "method": "official registry record (sponsor-reported)"}}
    return pv.stamp(ev, f"{API}/{t['nct_id']}", as_of)


def resolve_sponsor(sponsor, sec=None):
    """(ct query strings, alias dict or None). Unknown bare tickers are resolved via SEC company_tickers.json."""
    from trialwatch.core import sponsor_queries
    if not sponsor: return [None], None
    al = None
    try:
        from decisionwatch.core import resolve_company
        al = resolve_company(sponsor, sec)
    except Exception:
        al = None
    if al and al.get("known"): return sponsor_queries(sponsor), al
    if al and al.get("canonical") and al["canonical"] != sponsor:  # ticker -> SEC title, strip ", Inc."
        import re
        return [re.sub(r"[,.]?\s+(inc|corp|corporation|ltd|plc|co|llc)\.?$", "", al["canonical"], flags=re.I)], al
    return [sponsor], al


def readouts(client: CTGovClient, sponsor=None, condition=None, intervention=None, phases=DEFAULT_PHASES, statuses=ACTIVE,
             since=None, until=None, upcoming_days=None, industry_only=True, ticker_only=False, max_records=200,
             sec=None, today=None, as_of=None) -> list[dict]:
    """Upcoming (or windowed) primary-completion readouts, soonest first. Default window: today..today+90 days."""
    today = today or today_iso()
    since, until = _window(since, until, upcoming_days, today)
    if sec is not None and not pv._SEC_NAMES: pv.load_sec_tickers(sec)
    qs, al = resolve_sponsor(sponsor, sec)
    seen, out = set(), []
    as_of = as_of or pv.now_utc()
    for q in qs:
        for st in fetch(client, params(q, condition, intervention, phases, statuses, since, until, industry_only), max_records):
            t = normalize(st)
            if t["nct_id"] in seen: continue
            seen.add(t["nct_id"])
            ev = to_event(t, as_of, today)
            if al and al.get("ticker") and not ev["ticker"]:
                ev.update(ticker=al["ticker"], ticker_confidence=0.9 if al.get("known") else 0.8,
                          ticker_method="query_sponsor_" + ("alias" if al.get("known") else "sec"), ticker_company=al.get("canonical"))
                pv.stamp(ev, ev["source_url"], as_of)
            out.append(ev)
    if ticker_only: out = [e for e in out if e["ticker"]]
    out.sort(key=lambda e: (e["readout_date"] or "9999", e["nct_id"]))
    return out[:max_records]


def store(path: str) -> ItemStore:
    return ItemStore(path, "readout", TRACKED, new_kind="new_readout")


def run_watch(client, st: ItemStore, watch: str, **kw) -> dict:
    kw.setdefault("max_records", 1000)
    rows = readouts(client, **kw)
    snap = [{k: v for k, v in r.items() if k not in ("verified_as_of", "overdue")} for r in rows]
    info = st.ingest(watch, snap, query={k: v for k, v in kw.items() if k not in ("today", "sec", "as_of")})
    info["changes_detail"] = st.changes(watch=watch, run_id=info["run_id"])
    for c in info["changes_detail"]:
        if c["kind"] == "readout_date_change" and c["old"] and c["new"]:
            c["direction"] = "delayed" if c["new"] > c["old"] else "pulled_in"
    info["readouts"] = rows
    return info
