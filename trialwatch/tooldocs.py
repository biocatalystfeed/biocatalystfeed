"""Parameter descriptions and MCP tool annotations for the stdio server.

Every tool parameter gets a JSON-schema `description` (from PARAMS, with per-tool overrides in TOOL_PARAMS), and every
tool gets MCP ToolAnnotations so clients know what it does to the world:
  read     : calls a public source, changes nothing (readOnly, idempotent, open world)
  local    : reads changes already stored in the local snapshot DB; no network call (readOnly, idempotent, closed world)
  snapshot : calls a public source and writes a new snapshot run to the local DB (not read-only, not destructive:
             it only appends; calling it twice records two runs)
Descriptions are attached via typing.Annotated + pydantic Field on the function signature, which both mcp 1.x
(FastMCP) and 2.x (MCPServer) read when building the input schema."""
from __future__ import annotations
import inspect
from typing import Annotated

_DATE = "YYYY-MM-DD"
PARAMS: dict[str, str] = {
    "sponsor": "Sponsor/company name as free text (ClinicalTrials.gov query.spons). Known companies and tickers are alias-resolved, e.g. 'TERN' -> 'Terns, Inc.'.",
    "condition": "Condition or disease, free text (e.g. 'obesity', 'NASH').",
    "intervention": "Drug or intervention name, free text (e.g. 'semaglutide', 'VK2735').",
    "phases": "Trial phases to keep, any of EARLY_PHASE1, PHASE1, PHASE2, PHASE3, PHASE4, NA.",
    "statuses": "Overall statuses to keep, e.g. RECRUITING, ACTIVE_NOT_RECRUITING, COMPLETED, TERMINATED.",
    "changed_since": f"Only trials whose ClinicalTrials.gov record was updated on or after this date ({_DATE}).",
    "max_records": "Maximum number of records to return (capped server-side).",
    "max_results": "Maximum number of results to return (capped server-side).",
    "max_docs": "Maximum number of SEC documents to fetch and parse (capped at 25).",
    "exclude": "Drop results whose text fields contain any of these terms (whole word, case-insensitive; trailing * = prefix).",
    "rank": "If true, sort by relevance to the query terms instead of newest first.",
    "include_global": "Opt-in (default false): add labelled links to non-FDA/EMA registries or jurisdiction flags. Keep the label and global_disclaimer when showing them.",
    "global_sources": "With include_global: limit to these sources, subset of ['chictr', 'ictrp'].",
    "nct_id": "ClinicalTrials.gov ID: 'NCT' followed by 8 digits, e.g. NCT04184622.",
    "name": "Watch name: a label you choose for this saved query. Reuse the same name to diff against its previous snapshot.",
    "watch": "Only changes from this watch name (as given to the matching snapshot_* tool). Omit for all watches.",
    "since": f"Start date, inclusive ({_DATE}).",
    "until": f"End date, inclusive ({_DATE}).",
    "min_severity": "Drop lower-severity changes: 'notable' or 'critical'. Omit for all.",
    "application_number": "FDA application number, e.g. 'NDA215866' or 'BLA761269'.",
    "novel_only": "If true, only original approvals of new molecular entities / new BLAs.",
    "company": "Company name or ticker (alias-resolved for known companies).",
    "recent_days": "Window in days for 'recent' FDA actions and trial updates.",
    "include_collaborations": "If true, also keep trials where the company is only a collaborator, not the lead sponsor.",
    "basic": "If true, return only the trials + FDA part (faster; skips grants, papers, preprints and SEC).",
    "preprint_days": "Look back this many days for bioRxiv/medRxiv preprints; 0 skips preprints.",
    "org": "NIH RePORTER organization names (wildcard match unless org_exact).",
    "org_exact": "If true, org must match the RePORTER organization name exactly.",
    "pi": "Principal investigator, 'Jane A. Doe' or 'Doe, Jane A'.",
    "pi_exact": "If true, middle initials must match exactly (blank or different middle names are rejected).",
    "keyword": "Keyword or phrase (quote phrases; OR allowed where the source supports it).",
    "fiscal_years": "NIH fiscal years to include, e.g. [2025, 2026].",
    "include_future": "If false, drop awards whose notice date is after today.",
    "affiliation": "Author affiliation phrases, OR'd (e.g. 'Viking Therapeutics').",
    "drug": "Drug names or codes, OR'd.",
    "sources": "Paper sources, subset of ['pubmed', 'europepmc', 'preprints'] (default all).",
    "holder": "Marketing authorisation holder / applicant names, OR'd.",
    "status": "Status values to keep (source-specific; see the tool description).",
    "orphan": "If true, only orphan-designated medicines.",
    "prime": "If true, only medicines in EMA's PRIME scheme.",
    "area": "Committee areas, any of drugs, biologics, devices, tobacco, other (default all but tobacco).",
    "committee": "Advisory committee name or part of it (e.g. 'Oncologic Drugs').",
    "upcoming": "If true, keep only meetings dated today or later.",
    "agenda": "If true, fetch each notice's full text to parse agenda, NDA/BLA numbers and sponsors (one request per notice).",
    "application": "NDA/BLA number, e.g. 'NDA 218705', 'BLA 761308' or '218705'.",
    "topic": "Deficiency topics to keep: facility, product_quality, clinical, clinical_pharmacology, nonclinical, safety, human_factors.",
    "include_text": "If true, include the full OCR letter text (large).",
    "tool": "Which change store to read: trials, fda, grants, papers, sec, ema, adcom, crl, fda-decisions or readouts.",
    "kinds": "FDA decision event kinds to include, any of pdufa, adcom, approval, crl (default all).",
    "upcoming_days": "Only upcoming pdufa/adcom events from today to today+N days (overrides since/until; 0-730).",
    "format": "'json' (JSON Feed 1.1), 'rss' (RSS 2.0), 'markdown' or 'html' (rendered digest).",
    "industry_only": "If true (default), only trials whose lead sponsor class is INDUSTRY; false adds academic, NIH and other sponsors.",
    "ticker_only": "If true, keep only trials whose sponsor was matched to a stock ticker (see ticker_confidence).",
    "lookback_days": "Days back to look for newly stopped trials and passed primary completion dates (default 180).",
    "flags": "Keep only trials with any of these risk flags: stopped, overdue, stale_overdue, delayed, enrollment_shortfall, enrollment_cut.",
}

TOOL_PARAMS: dict[str, dict[str, str]] = {
    "sponsor_pipeline": {"sponsor": PARAMS["sponsor"]},
    "fda_approvals": {"sponsor": "Drugs@FDA sponsor; alias-resolved for known companies and tickers (e.g. 'Lilly', 'MDGL').",
                      "since": f"Submission status date from ({_DATE}).", "until": f"Submission status date to ({_DATE})."},
    "search_grants": {"since": f"Award notice date from ({_DATE}).", "until": f"Award notice date to ({_DATE})."},
    "snapshot_grants": {"since": f"Award notice date from ({_DATE})."},
    "search_papers": {"since": f"Publication date from ({_DATE}).", "keyword": "Raw query syntax for PubMed / Europe PMC."},
    "snapshot_papers": {"since": f"Publication date from ({_DATE}).", "keyword": "Raw query syntax for PubMed / Europe PMC."},
    "sec_pdufa_mentions": {"company": "Company name, ticker or SEC CIK.", "since": f"8-K filing date from ({_DATE}).",
                           "until": f"8-K filing date to ({_DATE})."},
    "ema_medicines": {"status": "EMA statuses, e.g. 'Opinion', 'Authorised', 'Refused', 'Withdrawn', 'Suspended'.",
                      "keyword": "Indication or therapeutic area text.", "since": f"Latest regulatory event date from ({_DATE}).",
                      "until": f"Latest regulatory event date to ({_DATE})."},
    "snapshot_ema": {"status": "EMA statuses, e.g. 'Opinion', 'Authorised'.", "since": f"Latest regulatory event date from ({_DATE})."},
    "fda_adcom_meetings": {"since": f"Notice publication date from ({_DATE}; default 365 days ago).",
                           "until": f"Notice publication date to ({_DATE}).", "keyword": "Matches title, agenda or sponsor (e.g. a drug or company)."},
    "snapshot_adcom": {"since": f"Notice publication date from ({_DATE}; default 365 days ago)."},
    "fda_complete_response_letters": {"company": "Company names, OR'd.", "status": "Application status: 'Approved' (approved since the letter) or 'Unapproved'.",
                                      "since": f"Letter date from ({_DATE}).", "until": f"Letter date to ({_DATE})."},
    "snapshot_crl": {"company": "Company names, OR'd.", "status": "'Approved' or 'Unapproved'.", "since": f"Letter date from ({_DATE})."},
    "fda_decisions": {"drug": "Drug name or code (e.g. 'tirzepatide', 'VK2735'); matched against filings, agendas, Drugs@FDA names and CRL text.",
                      "company": "Company name or ticker (alias-resolved; unknown US tickers are looked up in SEC's ticker list).",
                      "condition": "Condition / disease text (e.g. 'obesity'); coarse for approvals (Drugs@FDA has no indication field).",
                      "since": f"Event date from ({_DATE}).", "until": f"Event date to ({_DATE}).",
                      "max_docs": "Maximum SEC 8-K documents to parse for PDUFA dates (capped at 40)."},
    "readout_calendar": {"sponsor": "Lead sponsor name or ticker (alias-resolved; unknown US tickers looked up in SEC's ticker list), e.g. 'VKTX' or 'Viking Therapeutics'.",
                         "phases": "Phases to keep (default ['PHASE2','PHASE3']); any of EARLY_PHASE1, PHASE1, PHASE2, PHASE3, PHASE4, NA, or ['any'] for all.",
                         "since": f"Primary completion (readout) date from ({_DATE}).", "until": f"Primary completion (readout) date to ({_DATE}; default since + 365 days).",
                         "upcoming_days": "Readouts from today to today+N days (default 90 when since/until are omitted; 0-1095)."},
    "trials_at_risk": {"sponsor": "Lead sponsor name or ticker (alias-resolved).",
                       "phases": "Phases to keep (default ['PHASE2','PHASE3']); ['any'] for all."},
    "changes_feed": {"since": f"Only changes detected on or after this date ({_DATE})."},
}
for _t in ("trial_changes_since", "fda_changes_since", "grant_changes_since", "paper_changes_since", "ema_changes_since",
           "adcom_changes_since", "crl_changes_since", "fda_decision_changes_since", "readout_changes_since"):
    TOOL_PARAMS.setdefault(_t, {})["since"] = f"Only changes detected on or after this date ({_DATE})."

TOOL_PARAMS["snapshot_readouts"] = {k: v for k, v in TOOL_PARAMS["readout_calendar"].items() if k not in ("since", "until")}
TOOL_PARAMS["snapshot_fda_decisions"] = {k: v for k, v in TOOL_PARAMS["fda_decisions"].items() if k not in ("since", "until")}

KINDS = {
    "read": dict(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
    "local": dict(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    "snapshot": dict(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True),
}


def describe(fn):
    """Return fn with a __signature__ whose parameters carry Field(description=...)."""
    from pydantic import Field
    sig = inspect.signature(fn, eval_str=True)
    docs = {**PARAMS, **TOOL_PARAMS.get(fn.__name__, {})}
    ps = []
    for p in sig.parameters.values():
        d = docs.get(p.name)
        ps.append(p.replace(annotation=Annotated[p.annotation, Field(description=d)]) if d else p)
    fn.__signature__ = sig.replace(parameters=ps)
    return fn


def tool(server, kind: str):
    """Decorator: register fn on server with parameter descriptions and annotations (annotations skipped on SDKs
    that don't support them)."""
    def deco(fn):
        describe(fn)
        import functools
        orig = fn

        @functools.wraps(orig)
        def fn(*a, **k):  # every record returned carries verified_as_of / verify_hash / source_url / ticker_confidence
            from biowatch import provenance as pv
            res = orig(*a, **k)
            return pv.enrich(res) if not isinstance(res, str) else res
        fn.__signature__ = orig.__signature__
        try:
            from mcp.types import ToolAnnotations
            server.tool(annotations=ToolAnnotations(**KINDS[kind]))(fn)
        except (ImportError, TypeError):  # pragma: no cover (old mcp)
            server.tool()(fn)
        return fn
    return deco
