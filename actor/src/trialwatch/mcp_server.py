"""BioCatalystFeed MCP server (stdio): trials, FDA, grants, papers, SEC, EMA tools. Works with mcp SDK 1.x (FastMCP) and 2.x (MCPServer)."""
from __future__ import annotations
import os
try:
    from mcp.server import MCPServer as _Server  # mcp >= 2
except ImportError:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP as _Server  # mcp 1.x
from .client import CTGovClient
from .core import search, run_watch
from .normalize import normalize
from .report import sponsor_pipeline as _pipeline
from .store import Store

mcp = _Server("biocatalystfeed")
_client = CTGovClient()
from fdawatch.client import OpenFDAClient
_fda = OpenFDAClient()
_db = os.environ.get("BIOCATALYSTFEED_DB") or os.environ.get("TRIALWATCH_DB") or os.path.expanduser("~/.trialwatch.db")


def _clamp(n, hi: int, lo: int = 1) -> int:
    """MCP clients (LLMs) can pass any number; keep request sizes bounded so one call can't fan out unboundedly."""
    return max(lo, min(int(n), hi))


@mcp.tool()
def search_trials(sponsor: str | None = None, condition: str | None = None, intervention: str | None = None,
                  phases: list[str] | None = None, statuses: list[str] | None = None,
                  changed_since: str | None = None, max_records: int = 50, exclude: list[str] | None = None,
                  rank: bool = False) -> list[dict]:
    """Search ClinicalTrials.gov. phases e.g. ["PHASE2","PHASE3"]; statuses e.g. ["RECRUITING"]; changed_since YYYY-MM-DD.
    exclude drops trials whose title/conditions/interventions contain any term; rank sorts by relevance to the query."""
    from biowatch import filters
    rows = filters.exclude(search(_client, max_records=_clamp(max_records, 500), sponsor=sponsor, condition=condition,
                  intervention=intervention, phases=phases, statuses=statuses, changed_since=changed_since), exclude)
    return filters.rank(rows, condition, intervention, date_field="last_update_posted") if rank else rows


@mcp.tool()
def get_trial(nct_id: str) -> dict:
    """Get one normalized trial record by NCT ID."""
    return normalize(_client.get(nct_id))


@mcp.tool()
def snapshot_watch(name: str, sponsor: str | None = None, condition: str | None = None,
                   intervention: str | None = None, phases: list[str] | None = None) -> dict:
    """Snapshot a saved query ('watch') into the local DB and return what changed since its previous snapshot."""
    info = run_watch(_client, Store(_db), name, sponsor=sponsor, condition=condition, intervention=intervention, phases=phases)
    info.pop("trials")
    return info


@mcp.tool()
def trial_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """List detected changes (new trials, status/phase/enrollment/date changes) since an ISO date, optionally for one watch."""
    return Store(_db).changes(watch=watch, since=since)


@mcp.tool()
def sponsor_pipeline(sponsor: str, max_records: int = 300) -> dict:
    """Summarize a sponsor's trial pipeline by phase and status, with active trials sorted by primary completion."""
    return _pipeline(search(_client, sponsor=sponsor, max_records=_clamp(max_records, 1000)))


@mcp.tool()
def fda_approvals(sponsor: str | None = None, since: str | None = None, until: str | None = None,
                  application_number: str | None = None, novel_only: bool = False, max_results: int = 100) -> list[dict]:
    """Drugs@FDA submissions/approvals from openFDA (ORIG + supplements), newest first. sponsor is alias-resolved
    (e.g. 'Lilly', 'MDGL'); since/until filter submission status date YYYY-MM-DD; novel_only = original NME/BLA approvals."""
    from fdawatch.core import fda_approvals as _fa
    return _fa(_fda, sponsor=sponsor, since=since, until=until, application_number=application_number, novel_only=novel_only)[:_clamp(max_results, 1000)]


@mcp.tool()
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


@mcp.tool()
def fda_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """List detected FDA changes (new submissions, approvals, label revisions) since an ISO date (from fdawatch watches)."""
    from fdawatch.store import FDAStore
    return FDAStore(_db).changes(watch=watch, since=since)


@mcp.tool()
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


@mcp.tool()
def snapshot_grants(name: str, org: list[str] | None = None, pi: str | None = None, keyword: str | None = None,
                    since: str | None = None, org_exact: bool = False) -> dict:
    """Snapshot a grant query into the local DB; returns new awards / amount / end-date changes since the previous snapshot."""
    from grantwatch.core import ReporterClient, run_watch, store
    return run_watch(ReporterClient(), store(_db), name, org=org, pi=pi, keyword=keyword, since=since, org_exact=org_exact)


@mcp.tool()
def grant_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """Detected grant changes (new_award, award_amount_change, ...) since an ISO date."""
    from grantwatch.core import store
    return store(_db).changes(watch=watch, since=since)


@mcp.tool()
def search_papers(affiliation: list[str] | None = None, drug: list[str] | None = None, keyword: str | None = None,
                  since: str | None = None, preprint_days: int = 14, max_results: int = 50,
                  sources: list[str] | None = None, exclude: list[str] | None = None, rank: bool = False) -> dict:
    """Papers from PubMed, Europe PMC and bioRxiv/medRxiv preprints (via Europe PMC keyword search; bioRxiv API as
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
    return res


@mcp.tool()
def snapshot_papers(name: str, affiliation: list[str] | None = None, drug: list[str] | None = None,
                    keyword: str | None = None, since: str | None = None, preprint_days: int = 0) -> dict:
    """Snapshot a paper query (PubMed + optional preprints) and return papers new since the previous snapshot."""
    from paperwatch.core import PubMedClient, RxivClient, EuropePMCClient, run_watch, store
    return run_watch(PubMedClient(), RxivClient() if preprint_days > 0 else None, store(_db), name, affiliation, drug,
                     keyword, since=since, preprint_days=preprint_days, epmc=EuropePMCClient())


@mcp.tool()
def paper_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """New papers/preprints detected since an ISO date."""
    from paperwatch.core import store
    return store(_db).changes(watch=watch, since=since)


@mcp.tool()
def sec_pdufa_mentions(company: str, since: str | None = None, until: str | None = None, max_docs: int = 10) -> list[dict]:
    """SEC EDGAR 8-K documents mentioning "PDUFA" for a company (name, ticker or CIK), with candidate PDUFA dates and
    source links. Candidates are UNVERIFIED regex extractions; best=True marks the date nearest each mention."""
    from secwatch.core import SECClient, pdufa_mentions
    from secwatch.cli import _cik
    c = SECClient()
    return pdufa_mentions(c, _cik(c, company), since=since, until=until, max_docs=_clamp(max_docs, 25))


@mcp.tool()
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


@mcp.tool()
def snapshot_ema(name: str, holder: list[str] | None = None, drug: list[str] | None = None, keyword: str | None = None,
                 status: list[str] | None = None, since: str | None = None) -> dict:
    """Snapshot an EMA medicines query into the local DB; returns new medicines and status / opinion / EC decision /
    withdrawal changes since the previous snapshot. Data: European Medicines Agency (EMA)."""
    from emawatch.core import EMAClient, run_watch, store
    return run_watch(EMAClient(), store(_db), name, holder=holder, drug=drug, keyword=keyword, status=status, since=since)


@mcp.tool()
def ema_changes_since(since: str, watch: str | None = None) -> list[dict]:
    """Detected EMA changes (new_medicine, status_change, opinion_date_change, ec_decision_date_change, ...) since an ISO date."""
    from emawatch.core import store
    return store(_db).changes(watch=watch, since=since)


@mcp.tool()
def changes_feed(tool: str = "papers", since: str | None = None, watch: str | None = None, format: str = "json") -> str:
    """Digest of detected changes as a feed document (format 'json' = JSON Feed 1.1, 'rss' = RSS 2.0).
    tool: trials | fda | grants | papers | sec | ema."""
    if tool not in ("trials", "fda", "grants", "papers", "sec", "ema"):
        raise ValueError("tool must be one of trials, fda, grants, papers, sec, ema")
    if format not in ("json", "rss"): raise ValueError("format must be 'json' or 'rss'")
    from biowatch import digest
    import json as _json
    if tool == "trials": ch = Store(_db).changes(watch=watch, since=since)
    elif tool == "fda":
        from fdawatch.store import FDAStore; ch = FDAStore(_db).changes(watch=watch, since=since)
    else:
        mod = {"grants": "grantwatch", "papers": "paperwatch", "sec": "secwatch", "ema": "emawatch"}[tool]
        ch = __import__(f"{mod}.core", fromlist=["store"]).store(_db).changes(watch=watch, since=since)
    title = f"BioCatalystFeed {tool}: {watch or 'all watches'}"
    return digest.rss(title, ch) if format == "rss" else _json.dumps(digest.json_feed(title, ch), default=str)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
