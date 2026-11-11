"""BioCatalystFeed MCP server (stdio): trials, FDA, grants, papers, SEC, EMA, FDA AdCom, FDA CRL, FDA Orange Book, FDA decision calendar, trial readout calendar and Trials at Risk tools. Works with mcp SDK 1.x (FastMCP) and 2.x (MCPServer)."""
from __future__ import annotations
import os
try:
    from mcp.server import MCPServer as _Server  # mcp >= 2
except ImportError:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP as _Server  # mcp 1.x
from .client import CTGovClient
from .core import search, run_watch, raw_search
from .normalize import normalize
from .report import sponsor_pipeline as _pipeline
from .store import Store

INSTRUCTIONS = (
    "BioCatalystFeed: read-only public biotech data (ClinicalTrials.gov, openFDA, FDA Orange Book, Federal Register "
    "AdComs, EMA, NIH RePORTER, PubMed/Europe PMC/preprints, SEC EDGAR). Not investment, legal or medical advice; "
    "always cite the record's source_url. How to choose a tool: "
    "(1) one-off lookups use search_* / get_trial / fda_* / ema_medicines / orange_book_* / health_canada_notices / sec_pdufa_mentions "
    "(network, change nothing); "
    "(2) 'what is coming up' uses fda_decisions (PDUFA dates, AdComs, approvals, CRLs) and readout_calendar (trial "
    "primary completions); trials_at_risk flags stopped, overdue and slipping trials; company_profile merges everything "
    "for one company or ticker; "
    "(3) monitoring is two steps (list_watches shows existing watches): a snapshot_* tool stores a named query in the local DB and returns what changed since "
    "its previous run (the first run is a baseline), and the matching *_changes_since tool or changes_feed reads stored "
    "changes later without any network call. "
    "Company names and tickers are alias-resolved; every record carries verified_as_of, verify_hash, source_url and "
    "ticker_confidence. PDUFA dates are company-disclosed (SEC 8-K) and may move; trial dates labelled ESTIMATED can slip."
)
try:
    mcp = _Server("biocatalystfeed", instructions=INSTRUCTIONS)
except TypeError:  # pragma: no cover - very old SDKs without instructions
    mcp = _Server("biocatalystfeed")
from .tooldocs import tool as _tooldoc


def _tool(kind: str):
    return _tooldoc(mcp, kind)


_client = CTGovClient()
from fdawatch.client import OpenFDAClient
_fda = OpenFDAClient()
_db = os.environ.get("BIOCATALYSTFEED_DB") or os.environ.get("TRIALWATCH_DB") or os.path.expanduser("~/.trialwatch.db")


def _clamp(n, hi: int, lo: int = 1) -> int:
    """MCP clients (LLMs) can pass any number; keep request sizes bounded so one call can't fan out unboundedly."""
    return max(lo, min(int(n), hi))


@_tool("read")
def search_trials(sponsor: str | None = None, condition: str | None = None, intervention: str | None = None,
                  phases: list[str] | None = None, statuses: list[str] | None = None,
                  changed_since: str | None = None, max_records: int = 50, exclude: list[str] | None = None,
                  rank: bool = False, include_global: bool = False, global_sources: list[str] | None = None) -> list[dict] | dict:
    """Search clinical trials (ClinicalTrials.gov by default). sponsor is alias-resolved for known companies/tickers. Set `include_global: true` to also include links to records in non-FDA/EMA registries (China's ChiCTR, other WHO-listed national registries). Global results carry `registry_class: "non-FDA/EMA registry"` and a `global_disclaimer`. Off by default.
    Links (registry ID + URL from ClinicalTrials.gov secondary IDs) are in each trial's global_links. When showing global results to a user, keep the label
    and the disclaimer. include_global: Opt-in. Adds non-FDA/EMA sources that may follow different, sometimes lighter,
    regulatory standards. Results are labelled. Not an endorsement or medical or investment advice.
    phases e.g. ["PHASE2","PHASE3"]; statuses e.g. ["RECRUITING"]; changed_since YYYY-MM-DD; global_sources subset of
    ["chictr","ictrp"]. exclude drops trials whose title/conditions/interventions contain any term; rank sorts
    by relevance to the query."""
    from biowatch import filters, globalcov as gc
    q = dict(sponsor=sponsor, condition=condition, intervention=intervention, phases=phases, statuses=statuses,
             changed_since=changed_since)
    if include_global:
        srcs = gc.parse_sources(global_sources)
        rows = []
        for st in raw_search(_client, max_records=_clamp(max_records, 500), extra_fields=["SecondaryIdInfo"], **q):
            r = normalize(st); r["global_links"] = gc.registry_links(gc.secondary_ids(st), r["nct_id"], srcs); rows.append(r)
    else:
        rows = search(_client, max_records=_clamp(max_records, 500), **q)
    rows = filters.exclude(rows, exclude)
    if rank: rows = filters.rank(rows, condition, intervention, date_field="last_update_posted")
    if not include_global: return rows
    out = {"trials": rows}
    if any(r["global_links"] for r in rows): out["global_disclaimer"] = gc.GLOBAL_DISCLAIMER
    return out


@_tool("read")
def get_trial(nct_id: str) -> dict:
    """Get one normalized trial record by NCT ID. Same fields as search_trials results; a malformed ID returns an error."""
    return normalize(_client.get(nct_id))


@_tool("snapshot")
def snapshot_watch(name: str, sponsor: str | None = None, condition: str | None = None,
                   intervention: str | None = None, phases: list[str] | None = None) -> dict:
    """Trials only (ClinicalTrials.gov): snapshot a saved trial query ('watch') into the local DB and return what changed since its previous snapshot. For other sources use the matching snapshot_* tool (snapshot_readouts, snapshot_fda_decisions, snapshot_papers ...). Writes a run to the local DB (BIOCATALYSTFEED_DB); the first call for a name is a baseline with no changes. Use search_trials for one-off lookups and trial_changes_since to read stored changes later. sponsor is alias-resolved like search_trials."""
    info = run_watch(_client, Store(_db), name, sponsor=sponsor, condition=condition, intervention=intervention, phases=phases)
    info.pop("trials")
    return info


@_tool("local")
def trial_changes_since(since: str, watch: str | None = None, min_severity: str | None = None) -> list[dict]:
    """List detected changes since an ISO date, optionally for one watch: new trials and status, phase, enrollment,
    date, primary-endpoint, arm, intervention, site-count and results-posted changes. Each change has a severity
    (critical = terminated/suspended/withdrawn, why-stopped added, primary endpoint rewritten; notable; minor) and date
    changes carry shift_days. min_severity ('notable' or 'critical') drops lower levels. Reads the local snapshot DB only (no network call); changes exist only after snapshot_watch has run at least twice for a watch."""
    return Store(_db).changes(watch=watch, since=since, min_severity=min_severity)


@_tool("read")
def sponsor_pipeline(sponsor: str, max_records: int = 300) -> dict:
    """Summarize a sponsor's trial pipeline by phase and status, with active trials sorted by primary completion. sponsor is alias-resolved (company name or ticker, e.g. 'TERN')."""
    return _pipeline(search(_client, sponsor=sponsor, max_records=_clamp(max_records, 1000)))


@_tool("read")
def fda_approvals(sponsor: str | None = None, since: str | None = None, until: str | None = None,
                  application_number: str | None = None, novel_only: bool = False, max_results: int = 100) -> list[dict]:
    """Drugs@FDA submissions/approvals from openFDA (ORIG + supplements), newest first. sponsor is alias-resolved
    (e.g. 'Lilly', 'MDGL'); since/until filter submission status date YYYY-MM-DD; novel_only = original NME/BLA approvals."""
    from fdawatch.core import fda_approvals as _fa
    return _fa(_fda, sponsor=sponsor, since=since, until=until, application_number=application_number, novel_only=novel_only)[:_clamp(max_results, 1000)]


@_tool("read")
def company_profile(company: str, recent_days: int = 365, include_collaborations: bool = False, basic: bool = False,
                    preprint_days: int = 7) -> dict:
    """Merged company view: ClinicalTrials.gov pipeline (lead sponsor, alias-resolved) + FDA applications, novel approvals,
    recent FDA actions and label updates, plus (unless basic=True) NIH grants, PubMed papers (affiliation + key drugs),
    bioRxiv/medRxiv preprints via Europe PMC (last preprint_days; 0 = skip) and SEC 8-K PDUFA-date
    candidates (UNVERIFIED). Accepts name or ticker (e.g. 'Viking Therapeutics', 'TERN')."""
    from fdawatch.core import company_profile as _cp
    from grantwatch.core import ReporterClient
    from paperwatch.core import PubMedClient, RxivClient, EuropePMCClient
    from secwatch.core import SECClient
    kw = {} if basic else dict(grant_client=ReporterClient(), pubmed_client=PubMedClient(), sec_client=SECClient(),
                               rxiv_client=RxivClient() if preprint_days > 0 else None, preprint_days=max(preprint_days, 1),
                               epmc_client=EuropePMCClient() if preprint_days > 0 else None)
    return _cp(_client, _fda, company, recent_days=recent_days, include_collaborations=include_collaborations, **kw)


@_tool("local")
def fda_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """Drugs@FDA submission and label changes only (new submissions, approvals, label revisions) since an ISO date, from `bcf fda watch` (fdawatch) CLI watches. Not the FDA decision calendar: for PDUFA / AdCom / CRL / approval event changes recorded by snapshot_fda_decisions use fda_decision_changes_since. Reads the local snapshot DB only (no network call); changes exist only after the fdawatch CLI watch has run at least twice for a watch. Returns a list of change records {watch, key, kind, field, old, new, title, url, detected_at, run_id}, oldest first; an empty list means no changes were stored since that date. Create or refresh the watch with the fdawatch CLI (`bcf fda watch`)."""
    from fdawatch.store import FDAStore
    return FDAStore(_db).changes(watch=watch, since=since)


@_tool("read")
def search_grants(org: list[str] | None = None, pi: str | None = None, keyword: str | None = None,
                  since: str | None = None, until: str | None = None, fiscal_years: list[int] | None = None,
                  org_exact: bool = False, max_results: int = 100, pi_exact: bool = False, exclude: list[str] | None = None,
                  rank: bool = False, include_future: bool = True) -> list[dict]:
    """NIH RePORTER grants by organization (wildcard unless org_exact), PI name ('Jane A. Doe' or 'Doe, Jane A'; middle
    initials respected, pi_exact for strict), keyword (title/terms/abstract; quote phrases, OR allowed) and award notice
    date window YYYY-MM-DD. Newest award notice first; future-dated awards flagged and listed after current ones
    (include_future=False drops them). exclude drops grants mentioning any term; rank sorts by relevance."""
    from grantwatch.core import ReporterClient, search_grants as _sg
    return _sg(ReporterClient(), org=org, pi=pi, keyword=keyword, since=since, until=until, fiscal_years=fiscal_years,
               org_exact=org_exact, max_records=_clamp(max_results, 500), pi_exact=pi_exact, exclude=exclude, rank=rank,
               include_future=include_future)


@_tool("snapshot")
def snapshot_grants(name: str, org: list[str] | None = None, pi: str | None = None, keyword: str | None = None,
                    since: str | None = None, org_exact: bool = False) -> dict:
    """Snapshot a grant query into the local DB; returns new awards / amount / end-date changes since the previous snapshot. Network call + local write: stores a new run under `name` in the local DB (BIOCATALYSTFEED_DB) and returns {run_id, baseline, records, changes, changes_detail}; the first call for a name is a baseline with no changes. Use search_grants for one-off lookups (no write) and grant_changes_since to re-read stored changes later."""
    from grantwatch.core import ReporterClient, run_watch, store
    return run_watch(ReporterClient(), store(_db), name, org=org, pi=pi, keyword=keyword, since=since, org_exact=org_exact)


@_tool("local")
def grant_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """Detected grant changes (new_award, award_amount_change, ...) since an ISO date. Reads the local snapshot DB only (no network call); changes exist only after snapshot_grants has run at least twice for a watch. Returns a list of change records {watch, key, kind, field, old, new, title, url, detected_at, run_id}, oldest first; an empty list means no changes were stored since that date. Create or refresh the watch with snapshot_grants."""
    from grantwatch.core import store
    return store(_db).changes(watch=watch, since=since)


@_tool("read")
def search_papers(affiliation: list[str] | None = None, drug: list[str] | None = None, keyword: str | None = None,
                  since: str | None = None, preprint_days: int = 14, max_results: int = 50,
                  sources: list[str] | None = None, exclude: list[str] | None = None, rank: bool = False,
                  include_global: bool = False, global_sources: list[str] | None = None) -> dict:
    """Search PubMed, Europe PMC and preprints. Set `include_global: true` to flag papers from studies run outside US/EU oversight (`jurisdiction_flag`). Off by default.
    include_global: Opt-in. Adds non-FDA/EMA sources that may follow different, sometimes lighter, regulatory
    standards. Results are labelled. Not an endorsement or medical or investment advice. Flags come from
    author-affiliation countries ("unknown" when none found); keep the label and global_disclaimer when showing them.
    Papers from PubMed, Europe PMC and bioRxiv/medRxiv preprints (via Europe PMC keyword search; bioRxiv API as
    fallback), deduplicated by DOI/PMID. sources subset of ["pubmed","europepmc","preprints"] (default all).
    affiliation/drug lists are OR'd; keyword is raw query syntax; since = YYYY-MM-DD. exclude drops titles containing
    any term; rank sorts by relevance. Metadata + links only."""
    from paperwatch.core import PubMedClient, RxivClient, EuropePMCClient, search_all
    src = set(sources or ["pubmed", "europepmc", "preprints"])
    epmc = EuropePMCClient() if src & {"europepmc", "preprints"} else None
    res = search_all(PubMedClient() if "pubmed" in src else None, epmc if "europepmc" in src else None, None,
                     affiliation, drug, keyword, since=since, preprint_days=0, max_records=_clamp(max_results, 500))
    if "preprints" in src and preprint_days > 0:
        from paperwatch.core import search_preprints_fast, combined
        pre = search_preprints_fast(epmc, RxivClient(), affiliation, drug, keyword, days=preprint_days, max_records=_clamp(max_results, 500))
        res["papers"] = res["papers"] + pre
    from paperwatch.core import combined
    res["papers"] = combined(res["papers"], (affiliation, drug, keyword), exclude, rank)
    if include_global:
        from biowatch import globalcov as gc
        gc.parse_sources(global_sources)
        try:
            affs = gc.lookup_affiliations(epmc or EuropePMCClient(), res["papers"])
        except Exception as e:
            affs = {}; res.setdefault("errors", {})["global_affiliations"] = f"{type(e).__name__}: {e}"
        gc.annotate_papers(res["papers"], affs)
        if any(gc.is_global(r) for r in res["papers"]): res["global_disclaimer"] = gc.GLOBAL_DISCLAIMER
    return res


@_tool("snapshot")
def snapshot_papers(name: str, affiliation: list[str] | None = None, drug: list[str] | None = None,
                    keyword: str | None = None, since: str | None = None, preprint_days: int = 0) -> dict:
    """Snapshot a paper query (PubMed + optional preprints) and return papers new since the previous snapshot. Network call + local write: stores a new run under `name` in the local DB (BIOCATALYSTFEED_DB) and returns {run_id, baseline, records, changes, changes_detail}; the first call for a name is a baseline with no changes. Use search_papers for one-off lookups (no write) and paper_changes_since to re-read stored changes later."""
    from paperwatch.core import PubMedClient, RxivClient, EuropePMCClient, run_watch, store
    return run_watch(PubMedClient(), RxivClient() if preprint_days > 0 else None, store(_db), name, affiliation, drug,
                     keyword, since=since, preprint_days=preprint_days, epmc=EuropePMCClient())


@_tool("local")
def paper_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """New papers/preprints detected since an ISO date. Reads the local snapshot DB only (no network call); changes exist only after snapshot_papers has run at least twice for a watch. Returns a list of change records {watch, key, kind, field, old, new, title, url, detected_at, run_id}, oldest first; an empty list means no changes were stored since that date. Create or refresh the watch with snapshot_papers."""
    from paperwatch.core import store
    return store(_db).changes(watch=watch, since=since)


@_tool("read")
def sec_pdufa_mentions(company: str, since: str | None = None, until: str | None = None, max_docs: int = 10) -> list[dict]:
    """SEC EDGAR 8-K documents mentioning "PDUFA" for a company (name, ticker or CIK), with candidate PDUFA dates and
    source links. Candidates are UNVERIFIED regex extractions; best=True marks the date nearest each mention."""
    from secwatch.core import SECClient, pdufa_mentions
    from secwatch.cli import _cik
    c = SECClient()
    return pdufa_mentions(c, _cik(c, company), since=since, until=until, max_docs=_clamp(max_docs, 25))


@_tool("read")
def ema_medicines(holder: list[str] | None = None, drug: list[str] | None = None, keyword: str | None = None,
                  status: list[str] | None = None, since: str | None = None, until: str | None = None,
                  orphan: bool = False, prime: bool = False, max_results: int = 100, exclude: list[str] | None = None,
                  rank: bool = False) -> list[dict]:
    """European Medicines Agency (EU) centrally authorised human medicines: CHMP opinions, EC authorisations,
    refusals, withdrawals, suspensions. Filter by holder/applicant, drug (name/INN/substance), keyword (indication or
    therapeutic area), status (e.g. 'Opinion', 'Authorised', 'Refused'), latest regulatory event date window
    YYYY-MM-DD, orphan / PRIME flags. Newest event first. Data: European Medicines Agency (EMA); cite EMA as the source."""
    from emawatch.core import EMAClient, search_medicines
    return search_medicines(EMAClient(), holder=holder, drug=drug, keyword=keyword, status=status, since=since, until=until,
                            orphan=orphan, prime=prime, max_records=_clamp(max_results, 500), exclude=exclude, rank=rank)


@_tool("snapshot")
def snapshot_ema(name: str, holder: list[str] | None = None, drug: list[str] | None = None, keyword: str | None = None,
                 status: list[str] | None = None, since: str | None = None) -> dict:
    """Snapshot an EMA medicines query into the local DB; returns new medicines and status / opinion / EC decision /
    withdrawal changes since the previous snapshot. Data: European Medicines Agency (EMA). Network call + local write: stores a new run under `name` in the local DB (BIOCATALYSTFEED_DB) and returns {run_id, baseline, records, changes, changes_detail}; the first call for a name is a baseline with no changes. Use ema_medicines for one-off lookups (no write) and ema_changes_since to re-read stored changes later."""
    from emawatch.core import EMAClient, run_watch, store
    return run_watch(EMAClient(), store(_db), name, holder=holder, drug=drug, keyword=keyword, status=status, since=since)


@_tool("local")
def ema_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """Detected EMA changes (new_medicine, status_change, opinion_date_change, ec_decision_date_change, ...) since an ISO date. Reads the local snapshot DB only (no network call); changes exist only after snapshot_ema has run at least twice for a watch. Returns a list of change records {watch, key, kind, field, old, new, title, url, detected_at, run_id}, oldest first; an empty list means no changes were stored since that date. Create or refresh the watch with snapshot_ema."""
    from emawatch.core import store
    return store(_db).changes(watch=watch, since=since)


@_tool("read")
def fda_adcom_meetings(since: str | None = None, until: str | None = None, area: list[str] | None = None,
                       committee: str | None = None, keyword: str | None = None, upcoming: bool = False,
                       agenda: bool = True, max_results: int = 25, exclude: list[str] | None = None) -> list[dict]:
    """FDA advisory committee (AdCom) meeting notices from the Federal Register: committee, meeting date, kind
    (meeting / amendment / postponement / cancellation), and, parsed from the notice's agenda, the NDA/BLA numbers and
    sponsors under discussion. since/until filter the notice publication date (YYYY-MM-DD; default last 365 days).
    area: drugs, biologics, devices, tobacco, other (default all but tobacco). upcoming=True keeps meetings dated today
    or later. keyword matches title/agenda/sponsor (e.g. a drug or company). agenda=True costs one request per notice.
    Source: Federal Register (U.S. government, public domain); check the notice and fda.gov for late changes."""
    from datetime import date, timedelta
    from adcomwatch.core import FRClient, meetings
    return meetings(FRClient(), since=since or (date.today() - timedelta(days=365)).isoformat(), until=until, area=area,
                    committee=committee, keyword=keyword, upcoming=upcoming, agenda=agenda,
                    max_records=_clamp(max_results, 100), exclude=exclude)


@_tool("snapshot")
def snapshot_adcom(name: str, since: str | None = None, area: list[str] | None = None, committee: str | None = None,
                   keyword: str | None = None) -> dict:
    """Snapshot FDA advisory committee notices into the local DB; returns new notices (new meetings, amendments,
    postponements, cancellations) and meeting-date changes since the previous snapshot. Source: Federal Register. Network call + local write: stores a new run under `name` in the local DB (BIOCATALYSTFEED_DB) and returns {run_id, baseline, records, changes, changes_detail}; the first call for a name is a baseline with no changes. Use fda_adcom_meetings for one-off lookups (no write) and adcom_changes_since to re-read stored changes later."""
    from datetime import date, timedelta
    from adcomwatch.core import FRClient, run_watch, store
    return run_watch(FRClient(), store(_db), name, since=since or (date.today() - timedelta(days=365)).isoformat(),
                     area=area, committee=committee, keyword=keyword)


@_tool("local")
def adcom_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """Detected FDA advisory committee changes (new_notice, meeting_date_change, ...) since an ISO date. Reads the local snapshot DB only (no network call); changes exist only after snapshot_adcom has run at least twice for a watch. Returns a list of change records {watch, key, kind, field, old, new, title, url, detected_at, run_id}, oldest first; an empty list means no changes were stored since that date. Create or refresh the watch with snapshot_adcom."""
    from adcomwatch.core import store
    return store(_db).changes(watch=watch, since=since)


@_tool("read")
def fda_complete_response_letters(company: list[str] | None = None, application: str | None = None,
                                  since: str | None = None, until: str | None = None, status: list[str] | None = None,
                                  keyword: str | None = None, topic: list[str] | None = None, max_results: int = 25,
                                  exclude: list[str] | None = None, include_text: bool = False) -> list[dict]:
    """FDA complete response letters (CRLs) for NDAs/BLAs from openFDA, newest letter first: company, application
    number, best-effort product name, letter date, application_status ('Approved' = approved since, 'Unapproved' =
    not yet), deficiency topics (facility, product_quality, clinical, clinical_pharmacology, nonclinical, safety,
    human_factors) parsed from the letter's section headings, an excerpt of the first deficiency, and the PDF link.
    since/until filter the letter date (YYYY-MM-DD). application: 'NDA 218705', 'BLA 761308' or '218705'.
    keyword matches drug/product/company or any word in the letter. include_text adds the full OCR text (large).
    FDA publishes CRLs with a lag and redactions. Source: FDA / openFDA (public domain)."""
    from crlwatch.core import letters
    return letters(_fda, since=since, until=until, company=company, application=application, status=status,
                   keyword=keyword, topic=topic, exclude=exclude, include_text=include_text,
                   max_records=_clamp(max_results, 200))


@_tool("snapshot")
def snapshot_crl(name: str, company: list[str] | None = None, since: str | None = None, keyword: str | None = None,
                 status: list[str] | None = None) -> dict:
    """Snapshot FDA complete response letters into the local DB; returns new letters and application_status flips
    (Unapproved -> Approved) since the previous snapshot. Source: FDA / openFDA. Network call + local write: stores a new run under `name` in the local DB (BIOCATALYSTFEED_DB) and returns {run_id, baseline, records, changes, changes_detail}; the first call for a name is a baseline with no changes. Use fda_complete_response_letters for one-off lookups (no write) and crl_changes_since to re-read stored changes later."""
    from crlwatch.core import run_watch, store
    return run_watch(_fda, store(_db), name, company=company, since=since, keyword=keyword, status=status)


@_tool("local")
def crl_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """Detected FDA CRL changes (new_letter, application_status_change, ...) since an ISO date. Reads the local snapshot DB only (no network call); changes exist only after snapshot_crl has run at least twice for a watch. Returns a list of change records {watch, key, kind, field, old, new, title, url, detected_at, run_id}, oldest first; an empty list means no changes were stored since that date. Create or refresh the watch with snapshot_crl."""
    from crlwatch.core import store
    return store(_db).changes(watch=watch, since=since)


_ob = None


def _orange_book():
    global _ob
    if _ob is None:
        from obwatch.core import OrangeBookClient
        _ob = OrangeBookClient()
    return _ob


@_tool("read")
def orange_book_protections(company: list[str] | None = None, ingredient: list[str] | None = None,
                            trade_name: list[str] | None = None, application: str | None = None,
                            kind: list[str] | None = None, since: str | None = None, until: str | None = None,
                            upcoming_days: int | None = None, include_expired: bool = False, keyword: str | None = None,
                            exclude: list[str] | None = None, max_results: int = 50) -> list[dict]:
    """FDA Orange Book patent and exclusivity listings for NDAs/ANDAs, soonest expiry first: application, brand,
    ingredient, applicant, kind (patent / exclusivity), code (patent number, '*PED' = pediatric extension; or
    exclusivity code such as NCE, ODE, PED, NP, M-xx, I-xxx, D-xxx, PC, CGT), expiry date, drug substance / drug
    product flags, patent use codes, delist flag, product numbers and the Orange Book page. Patents are as listed by
    the applicant; FDA does not verify them, and actual generic entry can differ (litigation, settlements, 30-month
    stays). Data refreshes monthly. Source: FDA Orange Book data files (public domain)."""
    from obwatch.core import protections
    return protections(_orange_book(), company=company, ingredient=ingredient, trade_name=trade_name,
                       application=application, kind=kind, since=since, until=until,
                       upcoming_days=None if upcoming_days is None else _clamp(upcoming_days, 3650, 0),
                       include_expired=include_expired, keyword=keyword, exclude=exclude, max_records=_clamp(max_results, 500))


@_tool("read")
def orange_book_loe(company: list[str] | None = None, ingredient: list[str] | None = None,
                    trade_name: list[str] | None = None, application: str | None = None, since: str | None = None,
                    until: str | None = None, upcoming_days: int | None = None, keyword: str | None = None,
                    exclude: list[str] | None = None, max_results: int = 50) -> list[dict]:
    """Loss-of-exclusivity view from the FDA Orange Book: one row per application with its last listed protection
    (latest unexpired patent or exclusivity expiry and which one), counts of listed patents and exclusivities, soonest
    first. since/until/upcoming_days filter the individual listings first. This is when no *listed* protection blocks
    generics any more, not a prediction of generic launch. Source: FDA Orange Book data files (public domain)."""
    from obwatch.core import loe
    return loe(_orange_book(), company=company, ingredient=ingredient, trade_name=trade_name, application=application,
               since=since, until=until, upcoming_days=None if upcoming_days is None else _clamp(upcoming_days, 3650, 0),
               keyword=keyword, exclude=exclude, max_records=_clamp(max_results, 500))


@_tool("snapshot")
def snapshot_orange_book(name: str, company: list[str] | None = None, ingredient: list[str] | None = None,
                         trade_name: list[str] | None = None, until: str | None = None) -> dict:
    """Snapshot FDA Orange Book patent/exclusivity listings into the local DB; returns new listings and changed expiry
    dates, delist flags, drug substance/product flags and use codes since the previous snapshot. Source: FDA Orange Book. Network call + local write: stores a new run under `name` in the local DB (BIOCATALYSTFEED_DB) and returns {run_id, baseline, records, changes, changes_detail}; the first call for a name is a baseline with no changes. Use orange_book_protections for one-off lookups (no write) and orange_book_changes_since to re-read stored changes later."""
    from obwatch.core import run_watch, store
    return run_watch(_orange_book(), store(_db), name, company=company, ingredient=ingredient, trade_name=trade_name, until=until)


@_tool("local")
def orange_book_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """Detected Orange Book changes (new_listing, expires_change, delisted_change, ...) since an ISO date. Reads the local snapshot DB only (no network call); changes exist only after snapshot_orange_book has run at least twice for a watch. Returns a list of change records {watch, key, kind, field, old, new, title, url, detected_at, run_id}, oldest first; an empty list means no changes were stored since that date. Create or refresh the watch with snapshot_orange_book."""
    from obwatch.core import store
    return store(_db).changes(watch=watch, since=since)

_hc = None


def _health_canada():
    global _hc
    if _hc is None:
        from hcwatch.core import NOCClient
        _hc = NOCClient()
    return _hc


@_tool("read")
def health_canada_notices(company: list[str] | None = None, ingredient: list[str] | None = None,
                          brand: list[str] | None = None, submission: list[str] | None = None,
                          new_active_substance: bool = False, with_conditions: bool = False, priority: bool = False,
                          since: str | None = None, until: str | None = None, recent_days: int | None = None,
                          keyword: str | None = None, include_admin: bool = False, include_veterinary: bool = False,
                          exclude: list[str] | None = None, max_results: int = 50) -> list[dict]:
    """Health Canada Notices of Compliance (NOCs): Canadian drug and biologic approvals, newest first: NOC number and
    date, manufacturer, brand names, DINs, medicinal ingredients, submission (NDS new drug, SNDS supplement, ANDS
    generic, SANDS generic supplement), submission class, new_active_substance, priority, with_conditions (NOC/c,
    confirmatory studies required), reason (e.g. new indication), Canadian reference product for generics, and the NOC
    database page. Administrative NOCs and veterinary drugs are excluded unless asked for. Updated nightly by Health
    Canada; the tables are cached locally for 24 h. Source: Health Canada Notice of Compliance Database (Open
    Government Licence - Canada)."""
    from hcwatch.core import notices
    return notices(_health_canada(), company=company, ingredient=ingredient, brand=brand, submission=submission,
                   new_active_substance=new_active_substance, with_conditions=with_conditions, priority=priority,
                   since=since, until=until, recent_days=None if recent_days is None else _clamp(recent_days, 11000, 0),
                   keyword=keyword, include_admin=include_admin, include_veterinary=include_veterinary,
                   exclude=exclude, max_records=_clamp(max_results, 500))


@_tool("snapshot")
def snapshot_health_canada(name: str, company: list[str] | None = None, ingredient: list[str] | None = None,
                           submission: list[str] | None = None, new_active_substance: bool = False) -> dict:
    """Snapshot Health Canada Notices of Compliance (last 365 days) into the local DB; returns new NOCs and changes to
    date, active status (suspensions), NOC/c status, brand names and ingredients since the previous snapshot. Source:
    Health Canada NOC Database. Network call + local write: stores a new run under `name` in the local DB (BIOCATALYSTFEED_DB) and returns {run_id, baseline, records, changes, changes_detail}; the first call for a name is a baseline with no changes. Use health_canada_notices for one-off lookups (no write) and health_canada_changes_since to re-read stored changes later."""
    from hcwatch.core import run_watch, store
    return run_watch(_health_canada(), store(_db), name, company=company, ingredient=ingredient, submission=submission,
                     new_active_substance=new_active_substance)


@_tool("local")
def health_canada_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """Detected Health Canada NOC changes (new_noc, active_change, with_conditions_change, ...) since an ISO date. Reads the local snapshot DB only (no network call); changes exist only after snapshot_health_canada has run at least twice for a watch. Returns a list of change records {watch, key, kind, field, old, new, title, url, detected_at, run_id}, oldest first; an empty list means no changes were stored since that date. Create or refresh the watch with snapshot_health_canada."""
    from hcwatch.core import store
    return store(_db).changes(watch=watch, since=since)


def _dec_clients():
    from adcomwatch.core import FRClient
    from secwatch.core import SECClient
    return _fda, FRClient(), SECClient()


@_tool("read")
def fda_decisions(drug: str | None = None, company: str | None = None, condition: str | None = None,
                  kinds: list[str] | None = None, since: str | None = None, until: str | None = None,
                  upcoming_days: int | None = None, max_results: int = 50, max_docs: int = 20) -> dict:
    """FDA decision calendar: upcoming and recent FDA decision events in one list, upcoming soonest first, then past
    newest first. Kinds: 'pdufa' = PDUFA / target action dates disclosed by companies in SEC 8-K filings (FDA does not
    publish them; confidence 'company-disclosed', UNVERIFIED regex extraction - read the linked filing), 'adcom' = FDA
    advisory committee meetings from Federal Register notices (confidence 'scheduled'; status scheduled / postponed /
    cancelled / held), 'approval' = original approvals and efficacy supplements from Drugs@FDA (confidence 'confirmed'),
    'crl' = complete response letters from openFDA (confirmed, published with a lag). Each event has date,
    date_precision (day/month/quarter/half), confidence, status, company, ticker, drug, title, url (official record) and
    provenance {source, field, method}. Use this for "what FDA decisions are coming for X"; use snapshot_fda_decisions to
    watch for new events and moved dates. Returns {events, errors}; a failing source is listed in errors and the
    others still return. Scheduling/reference data, not investment advice."""
    from decisionwatch.core import decisions
    errors: list = []
    ev = decisions(*_dec_clients(), kinds=kinds, drug=drug, company=company, condition=condition, since=since, until=until,
                   upcoming_days=None if upcoming_days is None else _clamp(upcoming_days, 730, 0),
                   max_records=_clamp(max_results, 300), max_docs=_clamp(max_docs, 40), errors=errors)
    return {"events": ev, "errors": errors}


@_tool("snapshot")
def snapshot_fda_decisions(name: str, drug: str | None = None, company: str | None = None, condition: str | None = None,
                           kinds: list[str] | None = None, upcoming_days: int | None = None, max_docs: int = 20) -> dict:
    """Snapshot FDA decision events (same filters as fda_decisions) into the local DB and return what changed since
    the previous snapshot of this watch name: new_decision_event (a new PDUFA date disclosed, AdCom scheduled, approval
    or CRL published), date_change (e.g. a PDUFA date moved by a later 8-K, an AdCom rescheduled), status_change
    (pending -> date_passed, scheduled -> postponed/cancelled, CRL complete_response -> approved_since) and
    confidence_change. The first run is a baseline with no changes. Run it on a schedule (cron) for notifications;
    read results later with fda_decision_changes_since or changes_feed(tool='fda-decisions')."""
    from decisionwatch.core import run_watch, store
    return run_watch(*_dec_clients(), store(_db), name, kinds=kinds, drug=drug, company=company, condition=condition,
                     upcoming_days=None if upcoming_days is None else _clamp(upcoming_days, 730, 0), max_docs=_clamp(max_docs, 40))


@_tool("local")
def fda_decision_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """Detected FDA decision changes (new_decision_event, date_change, status_change, confidence_change) since an ISO
    date. Reads the local snapshot DB only (no network call); changes exist only after snapshot_fda_decisions has run
    at least twice for a watch. Returns a list of change records {watch, key, kind, field, old, new, title, url, detected_at, run_id}, oldest first; an empty list means no changes were stored since that date. Create or refresh the watch with snapshot_fda_decisions."""
    from decisionwatch.core import store
    return store(_db).changes(watch=watch, since=since)


def _sec_client():
    from secwatch.core import SECClient
    return SECClient()


def _phases(phases):
    from readoutwatch.core import DEFAULT_PHASES
    return DEFAULT_PHASES if phases is None else (None if phases == ["any"] or phases == [] else phases)


@_tool("read")
def readout_calendar(sponsor: str | None = None, condition: str | None = None, intervention: str | None = None,
                     phases: list[str] | None = None, since: str | None = None, until: str | None = None,
                     upcoming_days: int | None = None, industry_only: bool = True, ticker_only: bool = False,
                     max_results: int = 100) -> list[dict]:
    """Market-wide clinical trial readout calendar from ClinicalTrials.gov: trials whose PRIMARY COMPLETION DATE (last
    participant examined for the primary outcome; top-line data usually follow weeks to months later) falls in the
    window, soonest first. Default: industry-sponsored PHASE2/PHASE3 trials that are active (not yet recruiting,
    recruiting, enrolling by invitation, active not recruiting), next 90 days. Each record: nct_id, title, readout_date,
    date_precision (day/month), readout_date_type (ESTIMATED = sponsor's anticipated date, often slips; ACTUAL),
    completion_date, status, phase, sponsor, ticker, ticker_confidence (0-1), ticker_method, conditions, interventions,
    enrollment, primary_outcomes, overdue, url, and provenance fields verified_as_of, verify_hash, source_url. Use
    snapshot_readouts to watch for slips; trials_at_risk for stopped/overdue/delayed trials. Not investment advice."""
    from readoutwatch.core import readouts
    return readouts(_client, sponsor=sponsor, condition=condition, intervention=intervention, phases=_phases(phases),
                    since=since, until=until, upcoming_days=None if upcoming_days is None else _clamp(upcoming_days, 1095, 0),
                    industry_only=industry_only, ticker_only=ticker_only, max_records=_clamp(max_results, 1000), sec=_sec_client())


@_tool("snapshot")
def snapshot_readouts(name: str, sponsor: str | None = None, condition: str | None = None, intervention: str | None = None,
                      phases: list[str] | None = None, upcoming_days: int | None = None, industry_only: bool = True,
                      ticker_only: bool = False) -> dict:
    """Snapshot a readout-calendar query (same filters as readout_calendar) into the local DB and return what changed
    since the previous snapshot of this watch name: new_readout (a trial entered the window), readout_date_change
    (with direction 'delayed' or 'pulled_in'), readout_date_type_change (ESTIMATED -> ACTUAL: primary completion
    reached), status_change (e.g. -> SUSPENDED/TERMINATED), enrollment_change, phase_change. The first run is a baseline
    with no changes. Run on a schedule for notifications; history also powers trials_at_risk's delayed and enrollment
    flags. Read later with readout_changes_since or changes_feed(tool='readouts')."""
    from readoutwatch.core import run_watch, store
    info = run_watch(_client, store(_db), name, sponsor=sponsor, condition=condition, intervention=intervention,
                     phases=_phases(phases), upcoming_days=None if upcoming_days is None else _clamp(upcoming_days, 1095, 0),
                     industry_only=industry_only, ticker_only=ticker_only, sec=_sec_client())
    info.pop("readouts")
    return info


@_tool("local")
def readout_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """Detected readout changes (new_readout, readout_date_change, readout_date_type_change, status_change,
    enrollment_change, phase_change) since an ISO date. Reads the local snapshot DB only (no network call); changes
    exist only after snapshot_readouts has run at least twice for a watch. Returns a list of change records {watch, key, kind, field, old, new, title, url, detected_at, run_id}, oldest first; an empty list means no changes were stored since that date. Create or refresh the watch with snapshot_readouts."""
    from readoutwatch.core import store
    return store(_db).changes(watch=watch, since=since)


@_tool("read")
def trials_at_risk(sponsor: str | None = None, condition: str | None = None, intervention: str | None = None,
                   phases: list[str] | None = None, industry_only: bool = True, lookback_days: int = 180,
                   flags: list[str] | None = None, max_results: int = 100) -> list[dict]:
    """Trials at Risk: trials showing signs of delay or failure, highest risk_score first. Flags (severity 1-3):
    stopped (SUSPENDED/TERMINATED/WITHDRAWN, updated within lookback_days; why_stopped in detail), overdue (active trial
    whose ESTIMATED primary completion date passed), stale_overdue (overdue and record not updated for a year), and,
    from local snapshot history (needs snapshot_readouts), delayed (primary completion moved later), enrollment_shortfall
    (ACTUAL enrollment < 80% of the estimate) and enrollment_cut (target cut >= 20%). Each record has the
    readout_calendar fields plus risk_flags [{flag, severity, detail}] and risk_score. Not investment advice."""
    from readoutwatch.risk import trials_at_risk as _risk
    return _risk(_client, sponsor=sponsor, condition=condition, intervention=intervention, phases=_phases(phases),
                 industry_only=industry_only, lookback_days=_clamp(lookback_days, 1095), flags=flags,
                 db_path=_db if os.path.exists(_db) else None, max_records=_clamp(max_results, 500), sec=_sec_client())


@_tool("local")
def list_watches(tool: str | None = None) -> list[dict]:
    """List the watches (named saved queries) already stored in the local snapshot DB, newest run first: tool, watch name,
    number of runs, first/last run time, records in the last run, changes stored, the saved query, and which snapshot_* and
    *_changes_since tool to use for it. Call this before creating a watch (to reuse an existing name) or before reading
    changes (to find watch names). Reads the local DB only (no network call); an empty list means nothing has been watched yet.
    tool: optional filter, one of trials, fda, grants, papers, sec, ema, adcom, crl, orange-book, health-canada, fda-decisions, readouts."""
    from biowatch.watches import list_watches as _lw, TOOLS
    if tool is not None and tool not in {v[0] for v in TOOLS.values()}:
        raise ValueError("tool must be one of " + ", ".join(v[0] for v in TOOLS.values()))
    return _lw(_db, tool)


@_tool("local")
def changes_feed(tool: str = "papers", since: str | None = None, watch: str | None = None, format: str = "json") -> str:
    """Digest of detected changes as a document: format 'json' = JSON Feed 1.1, 'rss' = RSS 2.0, 'markdown' = rendered
    Markdown digest, 'html' = rendered standalone HTML digest (email-ready; nothing is sent).
    tool: trials | fda | grants | papers | sec | ema | adcom | crl | orange-book | health-canada | fda-decisions | readouts. Reads the local snapshot DB only (no network call)."""
    if tool not in ("trials", "fda", "grants", "papers", "sec", "ema", "adcom", "crl", "orange-book", "health-canada", "fda-decisions", "readouts"):
        raise ValueError("tool must be one of trials, fda, grants, papers, sec, ema, adcom, crl, orange-book, health-canada, fda-decisions, readouts")
    if format not in ("json", "rss", "markdown", "html"): raise ValueError("format must be 'json', 'rss', 'markdown' or 'html'")
    from biowatch import digest
    import json as _json
    if tool == "trials": ch = Store(_db).changes(watch=watch, since=since)
    elif tool == "fda":
        from fdawatch.store import FDAStore; ch = FDAStore(_db).changes(watch=watch, since=since)
    else:
        mod = {"grants": "grantwatch", "papers": "paperwatch", "sec": "secwatch", "ema": "emawatch", "adcom": "adcomwatch", "crl": "crlwatch", "orange-book": "obwatch", "health-canada": "hcwatch", "fda-decisions": "decisionwatch", "readouts": "readoutwatch"}[tool]
        ch = __import__(f"{mod}.core", fromlist=["store"]).store(_db).changes(watch=watch, since=since)
    title = f"BioCatalystFeed {tool}: {watch or 'all watches'}"
    if format == "markdown": return digest.markdown(title, ch)
    if format == "html": return digest.html(title, ch)
    return digest.rss(title, ch) if format == "rss" else _json.dumps(digest.json_feed(title, ch), default=str)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
