from __future__ import annotations

ATTR = ("_Sources: ClinicalTrials.gov API v2 (U.S. National Library of Medicine; clinicaltrials.gov/about-site/terms-conditions). "
        "Data provided by the U.S. Food and Drug Administration (https://open.fda.gov), CC0; openFDA results are unvalidated — "
        "do not rely on them for medical decisions. NIH RePORTER (NIH); PubMed via NCBI E-utilities (NLM); bioRxiv/medRxiv metadata (CSHL; "
        "preprint licences vary, links only); SEC EDGAR (public). PDUFA candidates are unverified extractions. Not investment advice._")


def profile_markdown(p: dict) -> str:
    t, f = p["trials"], p["fda"]
    L = [f"## {p['company']}" + (f" ({p['ticker']})" if p.get("ticker") else ""), "",
         f"As of {p['as_of']}. Aliases: CT.gov {p['aliases_used']['ct_queries']}, Drugs@FDA {p['aliases_used']['fda_sponsors'] or '—'}.", "",
         f"**Trials (lead sponsor):** {t['total']} total, {t['active']} active. Phases: " + ", ".join(f"{k} {v}" for k, v in t["by_phase"].items()), "",
         f"**FDA:** {f['applications']} applications, {f['original_approvals']} original approvals, {len(f['novel_approvals'])} novel (NME/BLA).", ""]
    if t["next_primary_completions"]:
        L += ["**Next primary completions (active trials):**", "", "| NCT | Phase | Status | Primary completion | Title |", "|---|---|---|---|---|"]
        L += [f"| [{x['nct_id']}](https://clinicaltrials.gov/study/{x['nct_id']}) | {x['phase'] or ''} | {x['status']} | {x['primary_completion_date'] or ''} | {(x['title'] or '')[:80]} |"
              for x in t["next_primary_completions"][:8]] + [""]
    if t["recently_stopped"]:
        L += ["**Stopped in window:** " + "; ".join(f"{x['nct_id']} {x['status']} ({(x['why_stopped'] or 'no reason')[:60]})" for x in t["recently_stopped"][:5]), ""]
    if f["novel_approvals"]:
        L += ["**Novel approvals:** " + "; ".join(f"{x['brand_names']} ({x['application_number']}, {x['submission_status_date']})" for x in f["novel_approvals"][:12]), ""]
    if f["recent_submissions"]:
        L += ["**FDA actions, last 12 months:**", "", "| Date | Application | Brand | Type | Class |", "|---|---|---|---|---|"]
        L += [f"| {x['submission_status_date']} | [{x['application_number']}]({x['url']}) | {x['brand_names'] or ''} | {x['submission_type']}{x['submission_number']} | {x['submission_class'] or ''} |"
              for x in f["recent_submissions"][:10]] + [""]
    if f["recent_label_updates"]:
        L += ["**Label (SPL) updates, last 12 months:** " + "; ".join(f"{x['brand_name']} v{x['version']} {x['effective_time']}" for x in f["recent_label_updates"][:8]), ""]
    L += _extra_md(p)
    if isinstance(p["pdufa"], str): L += [f"_PDUFA: {p['pdufa']}_", ""]
    return "\n".join(L)


def _extra_md(p: dict) -> list[str]:
    L = []
    g = p.get("grants")
    if isinstance(g, dict) and "error" not in g:
        L += [f"**NIH grants:** {g['org_grants_total']} to org {g['org_names'] or '(no RePORTER org configured)'}; "
              f"{g['drug_grants_total']} mentioning {', '.join(g['drug_terms'] or []) or '—'}.", ""]
        rows = g["org_grants_latest"][:3] + g["drug_grants_latest"][:5]
        if rows:
            L += ["| Notice date | Project | Org | PI | Amount | Title |", "|---|---|---|---|---|---|"]
            L += [f"| {r['award_notice_date'] or ''} | [{r['project_num']}]({r['url']}) | {r['org_name']} | {(r['pis'] or '')[:30]} | {r['award_amount'] or ''} | {(r['title'] or '')[:70]} |" for r in rows] + [""]
    elif g: L += [f"**NIH grants:** error {g['error']}", ""]
    pa = p.get("papers")
    if isinstance(pa, dict) and "error" not in pa:
        for lab, k in (("PubMed, company affiliation", "pubmed_affiliation"), ("PubMed, key drugs", "pubmed_drugs")):
            x = pa.get(k)
            if x:
                L += [f"**{lab}** since {pa['since']}: {x['total_since']} papers (`{x['term'][:90]}`)", ""]
                L += [f"- {r['date']} [{(r['title'] or '')[:110]}]({r['url']}) — {r['journal']}" for r in x["latest"][:5]] + [""]
        if pa.get("preprints") is not None:
            L += [f"**Preprints (bioRxiv/medRxiv, last {pa['preprint_window_days']} days):** {len(pa['preprints'])}", ""]
            L += [f"- {r['date']} [{(r['title'] or '')[:110]}]({r['url']}) — {r['source']}, {r.get('corresponding_institution') or ''}" for r in pa["preprints"][:5]] + [""]
    elif pa: L += [f"**Papers:** error {pa['error']}", ""]
    sec = p.get("sec")
    if isinstance(sec, dict) and sec.get("not_sec_registered"):
        L += [f"**SEC EDGAR:** {sec['message']}", ""]
    elif isinstance(sec, dict) and "error" not in sec:
        L += [f"**SEC EDGAR:** CIK {sec['cik']} ({sec['name']}), {sec['recent_8k_count']} 8-Ks in recent-filings list, latest {sec['latest_8k']}; "
              f"{len(sec['pdufa_mentions'])} 8-K documents mentioning \"PDUFA\" in window.", ""]
    elif sec: L += [f"**SEC EDGAR:** error {sec['error']}", ""]
    if isinstance(p.get("pdufa"), dict):
        L += ["**PDUFA date candidates — UNVERIFIED (regex from 8-K text; check source):**", "", "| Candidate | Filed | Source | Context |", "|---|---|---|---|"]
        L += [f"| {c['date']} | {c['filed']} | [filing]({c['url']}) | {c['context'][:150].replace('|', '/')} |" for c in p["pdufa"]["candidates"][:10]] + [""]
    return L


def approvals_markdown(rows: list[dict], title: str) -> str:
    L = [f"# {title}", "", "| Date | Application | Sponsor | Brand | Ingredient | Type | Class | Priority |", "|---|---|---|---|---|---|---|---|"]
    L += [f"| {r['submission_status_date']} | [{r['application_number']}]({r['url']}) | {r['sponsor']} | {r['brand_names'] or ''} | {(r['active_ingredients'] or '')[:40]} | {r['submission_type']}{r['submission_number']} | {r['submission_class'] or ''} | {r['review_priority'] or ''} |" for r in rows]
    return "\n".join(L + ["", ATTR])
