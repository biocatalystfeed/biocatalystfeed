"""High-level FDA operations and the cross-source company profile."""
from __future__ import annotations
from datetime import date, timedelta
from .aliases import resolve
from .client import OpenFDAClient
from .normalize import submissions, label, is_novel

ACTIVE = {"RECRUITING", "NOT_YET_RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"}


def fda_approvals(client: OpenFDAClient, sponsor: str | None = None, since: str | None = None, until: str | None = None,
                  application_number: str | None = None, novel_only: bool = False, max_apps: int = 500) -> list[dict]:
    """Drugs@FDA submissions (approvals incl. supplements), newest first. sponsor is alias-resolved;
    since/until filter the submission status date (YYYY-MM-DD)."""
    al = resolve(sponsor) if sponsor else None
    names = al["fda_sponsors"] if al else None
    if al is not None and not names:
        return []  # known company with no Drugs@FDA applications
    apps = client.drugsfda(sponsors=names, application_number=application_number, since=since, until=until, max_records=max_apps)
    if al and al.get("known"):
        allowed = {n.upper() for n in names}
        apps = [a for a in apps if (a.get("sponsor_name") or "").upper() in allowed]
    rows = [r for a in apps for r in submissions(a)]
    s, u = (since or "0000"), (until or "9999")
    rows = [r for r in rows if s <= (r["submission_status_date"] or "") <= u + "z"]
    if novel_only: rows = [r for r in rows if is_novel(r)]
    return sorted(rows, key=lambda r: r["submission_status_date"] or "", reverse=True)


def label_events(client: OpenFDAClient, sponsor: str | None = None, since: str | None = None, max_records: int = 100) -> list[dict]:
    al = resolve(sponsor) if sponsor else None
    mfrs = al["label_mfrs"] if al else None
    if al is not None and not mfrs: return []
    return [label(x) for x in client.labels(manufacturers=mfrs, since=since, max_records=max_records)]


def company_trials(ct_client, sponsor: str, max_records: int = 1000, include_collaborations: bool = False) -> tuple[list[dict], dict]:
    from trialwatch.core import search
    al = resolve(sponsor)
    seen: dict[str, dict] = {}
    for q in al["ct_queries"]:
        for r in search(ct_client, sponsor=q, max_records=max_records, sponsor_aliases=False):
            seen.setdefault(r["nct_id"], r)
    recs = list(seen.values())
    if al["ct_lead"] and not include_collaborations:
        recs = [r for r in recs if any(p in (r.get("lead_sponsor") or "").lower() for p in al["ct_lead"])]
    return recs, al


def company_profile(ct_client, fda_client: OpenFDAClient, sponsor: str, max_trials: int = 1000,
                    recent_days: int = 365, include_collaborations: bool = False, today: date | None = None,
                    grant_client=None, pubmed_client=None, rxiv_client=None, sec_client=None, epmc_client=None,
                    preprint_days: int = 14, sec_years: int = 3) -> dict:
    """Optional clients add sections: grant_client (NIH RePORTER), pubmed_client/rxiv_client (papers), sec_client (EDGAR
    PDUFA candidates). Each section is None when its client isn't passed; a failing source is reported as {'error': ...}."""
    from trialwatch.report import sponsor_pipeline
    today = today or date.today()
    since = (today - timedelta(days=recent_days)).isoformat()
    trials, al = company_trials(ct_client, sponsor, max_trials, include_collaborations)
    subs = fda_approvals(fda_client, sponsor=al["canonical"])
    labels = label_events(fda_client, sponsor=al["canonical"], since=since, max_records=100)
    pipe = sponsor_pipeline(trials)
    approved = [r for r in subs if r["submission_status"] == "APPROVED"]
    orig = [r for r in approved if r["submission_type"] == "ORIG"]
    upcoming = [t for t in pipe["active"] if (t["primary_completion_date"] or "") >= today.isoformat()[:7]]
    out = {
        "company": al["canonical"], "ticker": al.get("ticker"), "alias_known": al["known"],
        "aliases_used": {k: al.get(k) for k in ("ct_queries", "ct_lead", "fda_sponsors", "label_mfrs")},
        "as_of": today.isoformat(),
        "trials": {"total": pipe["total"], "by_phase": pipe["by_phase"], "by_status": pipe["by_status"],
                   "active": len(pipe["active"]),
                   "next_primary_completions": upcoming[:15],
                   "recently_stopped": sorted([{k: t.get(k) for k in ("nct_id", "phase", "status", "title", "why_stopped", "last_update_posted")}
                                               for t in trials if t.get("status") in ("TERMINATED", "SUSPENDED", "WITHDRAWN")
                                               and (t.get("last_update_posted") or "") >= since],
                                              key=lambda x: x["last_update_posted"] or "", reverse=True)},
        "fda": {"applications": len({r["application_number"] for r in subs}),
                "original_approvals": len(orig),
                "novel_approvals": [ {k: r[k] for k in ("application_number", "brand_names", "active_ingredients", "submission_status_date", "review_priority", "submission_class", "url")}
                                     for r in approved if is_novel(r)],
                "recent_submissions": [{k: r[k] for k in ("application_number", "brand_names", "submission_type", "submission_number", "submission_status", "submission_status_date", "submission_class", "url")}
                                       for r in subs if (r["submission_status_date"] or "") >= since][:25],
                "recent_label_updates": labels[:25]},
        "pdufa": "Not available: FDA does not publish PDUFA goal dates; they are company-disclosed (8-K/press). No public source with clear reuse terms is integrated.",
        "sources": ["ClinicalTrials.gov API v2 (NLM)", "openFDA drug/drugsfda + drug/label (FDA, CC0)"],
    }
    _extend_profile(out, al, today, since, grant_client, pubmed_client, rxiv_client, sec_client, preprint_days, sec_years, epmc_client)
    return out


def _safe(fn):
    try:
        return fn()
    except Exception as e:  # one flaky source shouldn't kill the profile
        return {"error": f"{type(e).__name__}: {e}"}


def _extend_profile(out, al, today, since, gc, pm, rx, sc, preprint_days, sec_years, epmc=None):
    if gc is not None:
        from grantwatch.core import company_grants, search_grants
        def g():
            org = company_grants(gc, al, max_records=200)
            drug = search_grants(gc, keyword=" OR ".join(f'"{d}"' for d in al["drugs"]), max_records=100) if al.get("drugs") else []
            pick = lambda r: {k: r[k] for k in ("project_num", "fiscal_year", "title", "org_name", "pis", "agency", "award_amount", "award_notice_date", "url")}
            return {"org_names": al.get("nih_orgs"), "org_grants_total": len(org), "org_grants_recent": [pick(r) for r in org if (r["award_notice_date"] or "") >= since][:10],
                    "org_grants_latest": [pick(r) for r in org[:5]],
                    "drug_terms": al.get("drugs"), "drug_grants_total": len(drug), "drug_grants_latest": [pick(r) for r in drug[:10]]}
        out["grants"] = _safe(g)
        out["sources"].append("NIH RePORTER API v2")
    if pm is not None:
        from paperwatch.core import company_papers
        def p():
            r = company_papers(pm, rx, al, since=since, preprint_days=preprint_days, max_records=25, epmc=epmc)
            sl = lambda x: None if x is None else {"term": x["term"], "total_since": x["total"], "latest": x["papers"][:10]}
            return {"since": since, "pubmed_affiliation": sl(r["pubmed_affiliation"]), "pubmed_drugs": sl(r["pubmed_drugs"]),
                    "preprints": r["preprints"][:15] if (rx or epmc) is not None else None, "preprint_window_days": preprint_days if (rx or epmc) is not None else None}
        out["papers"] = _safe(p)
        out["sources"].append("PubMed E-utilities (NLM)" + (" + Europe PMC (preprints)" if epmc is not None else "") + (" + bioRxiv/medRxiv API" if rx is not None else ""))
    if sc is not None:
        from secwatch.core import company_sec
        sec = _safe(lambda: company_sec(sc, al, since=(today - timedelta(days=365 * sec_years)).isoformat(), max_docs=10))
        out["sec"] = sec
        out["sources"].append("SEC EDGAR full-text search + submissions API")
        if isinstance(sec, dict) and sec.get("not_sec_registered"):
            out["pdufa"] = "Not available: " + sec["message"]
        elif isinstance(sec, dict) and "error" not in sec:
            out["pdufa"] = (f"No 8-K text mentioning 'PDUFA' found via EDGAR full-text search in the last {sec_years} years "
                            "(company may disclose dates only in press releases not furnished as 8-K exhibits).")
        if isinstance(sec, dict) and sec.get("pdufa_mentions"):
            c = [{"date": x.get("date_guess") or x["date_text"], "filed": m["file_date"], "url": m["url"], "context": x["context"][:240]}
                 for m in sec["pdufa_mentions"] for x in m["candidates"] if x.get("best")]
            if c: out["pdufa"] = {"status": "UNVERIFIED candidates extracted from SEC 8-K text - confirm in source", "candidates": c}


def run_fda_watch(client: OpenFDAClient, store, watch: str, sponsor: str | None = None, since: str | None = None,
                  labels: bool = True) -> dict:
    """Snapshot a sponsor's (or a date window's) submissions + labels and diff vs the previous snapshot."""
    subs = fda_approvals(client, sponsor=sponsor, since=since)
    labs = label_events(client, sponsor=sponsor, since=since) if labels and (sponsor or since) else []
    info = store.ingest(watch, subs, labs, query={"sponsor": sponsor, "since": since})
    info["changes_detail"] = store.changes(watch=watch, run_id=info["run_id"])
    return info
