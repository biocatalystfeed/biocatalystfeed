# BioCatalystFeed developer notes (formerly biotech-data-tools / trialwatch prototype)

> Historical design notes from the v0.1 prototype, kept for contributors. See the top-level README for current usage.

ClinicalTrials.gov (API v2) monitor: search by sponsor / condition / intervention / phase / status / last-update date, normalize records, and diff each run against the previous snapshot (SQLite) to surface **new trials, status changes (e.g. RECRUITING→TERMINATED), phase changes, enrollment changes, date slips**.

Three front-ends over one core (`trialwatch/`):
| Surface | Entry |
|---|---|
| CLI | `trialwatch` (`trialwatch/cli.py`) |
| MCP server (stdio, official `mcp` SDK; v2 `MCPServer`, falls back to v1 `FastMCP`) | `trialwatch-mcp` / `python -m trialwatch.mcp_server` |
| Apify-Actor layout (local only, not pushed) | `actor/` |

## Install
```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[mcp,dev]'
```
(Don't run Python from `/workspace` itself: a stray `/workspace/nt.py` shadows the stdlib.)

## CLI
```bash
trialwatch search --sponsor "Viking Therapeutics" --phase PHASE3
trialwatch search --condition obesity --phase PHASE2 PHASE3 --changed-since 2026-10-01 --csv out.csv
trialwatch get NCT07868939
trialwatch pipeline "Zealand Pharma"
# first run = baseline; later runs print/store the diff
trialwatch --db tw.db watch --name glp1 --condition obesity --intervention "semaglutide OR tirzepatide" --md glp1.md --changes-csv glp1_changes.csv
trialwatch --db tw.db changes --name glp1 --since 2026-10-01
```
Run `watch` daily by cron to get "what changed since last run".

## MCP server
Tools: `search_trials`, `get_trial`, `snapshot_watch`, `trial_changes_since`, `sponsor_pipeline`. DB path from `TRIALWATCH_DB` (default `~/.trialwatch.db`).
```json
{"mcpServers": {"trialwatch": {"command": "/workspace/biotech-data-tools/.venv/bin/trialwatch-mcp"}}}
```

## Apify Actor (local)
`actor/.actor/actor.json`, `actor/.actor/input_schema.json`, `actor/Dockerfile`, `actor/main.py`. Local run: `LOCAL=1 python actor/main.py` (reads `actor/input.json`, writes `actor/storage/output.json`). On Apify the snapshot DB persists in a named KV store and output goes to the dataset. Docker build context is the repo root (`docker build -f actor/Dockerfile .`); before an actual Apify push, the `trialwatch/` package must be copied into `actor/` or the Dockerfile pointed at it. **Not pushed; no Apify account exists.**

## Tests
`.venv/bin/python -m pytest -q` (19 offline + 3 live tests; `tests/test_biowatch.py`: RePORTER criteria/normalize, grant new_award + amount-change diff, PubMed term builder/normalize, preprint filtering (word boundary, latest version), paper new-item diff, PDUFA extraction (incl. dateline rejection, year inference), extended aliases, merged company_profile with fake clients, MCP lists the 7 new tools; fdawatch: normalization, novelty rule, query builders, aliases incl. Terns, FDA diff engine, offline company_profile with fake clients; offline: normalization, query building, diff engine with simulated status/phase/enrollment/date changes, MCP stdio tool listing). `TRIALWATCH_LIVE=1` adds a live API test.

## Samples (`samples/`, real data pulled 2026-10-12 PT)
- `obesity_baseline.md` / `obesity_trials.csv`: 371 Ph2/Ph3 obesity trials with incretin interventions (baseline snapshot)
- `obesity_recent_activity.md` / `obesity_updated_since_2026-10-01.csv`: 56 obesity Ph2/3 trials updated since Oct 1
- `zealand_pipeline.md` / `zealand_trials.csv`: Zealand Pharma (55 trials)
- `sample.db`: baselines for obesity watch + Viking, Structure, Zealand, Altimmune, Terns (Terns returned 0 — sponsor name mismatch to fix)

## fdawatch (openFDA) + company profiles — added 2026-10-12
Package `fdawatch/` (same style: client → normalize → store → core → cli/report; MCP tools live in the shared `trialwatch-mcp` server).
```bash
fdawatch approvals --sponsor Madrigal                 # all Drugs@FDA submissions (ORIG + supplements) for a sponsor
fdawatch approvals --since 2026-09-01 --novel --md novel.md   # recent original NME/BLA approvals, all sponsors
fdawatch labels --sponsor Lilly --since 2026-07-01    # SPL label versions (DailyMed links)
fdawatch profile "Viking Therapeutics" Lilly MDGL Terns --md profiles.md --json
fdawatch --db tw.db watch --name fda-lilly --sponsor Lilly   # snapshot; later runs diff
fdawatch --db tw.db changes --name fda-lilly --since 2026-10-01
fdawatch alias Terns                                  # show alias resolution
```
- **Change tracking**: tables `fda_records/fda_runs/fda_changes` (can share the trialwatch DB). Change kinds: `new_submission`, `approval`, `status_change`, `new_documents` (new letter/label/review PDF on a submission), `label_revision`, `new_label`, `date_change`, `field_change`.
- **Sponsor aliases** (`fdawatch/aliases.py`, override/extend with JSON at `$FDAWATCH_ALIASES`): canonical name/ticker → CT.gov query strings, lead-sponsor substrings (drops collaborator-only hits), exact Drugs@FDA `sponsor_name` values (openFDA uses abbreviations: `LILLY`, `ELI LILLY AND CO`, `MADRIGAL`, `NOVO`) and SPL manufacturer names. Fixes Terns: its CT.gov lead sponsor is now "Terns, Inc., a subsidiary of Merck & Co., Inc." → 7 trials (was 0).
- **MCP tools added**: `fda_approvals`, `company_profile`, `fda_changes_since`.
- **"Novel" flag** = ORIG approval with class "Type 1 - New Molecular Entity", or ORIG1 BLA not classed Type 5. Approximates FDA's CDER novel-approval list; CBER products and older BLAs without class codes are imperfect.
- **PDUFA dates: implemented in 0.3.5 as `decisionwatch` (company-disclosed 8-K extraction, labelled; see the 0.3.5 notes).** Original note: FDA does not publish goal dates; they appear in company press releases/8-Ks. Third-party PDUFA calendars (e.g. biopharmcatalyst, RTTNews, fdatracker) are proprietary/ToS-restricted, so none integrated. Possible permitted path: SEC EDGAR (public-domain US gov data; fair-access policy ≤10 req/s with a declared User-Agent) full-text search for "PDUFA" in 8-K exhibits — would need text extraction and is not built.
- Samples: `samples/company_profiles.md|json` (Viking, Lilly, Madrigal, Terns; real data 2026-10-12 PT), `samples/fda_novel_approvals_since_2026-09-01.md`, `samples/sample.db` now also holds FDA baselines `fda-lilly`, `fda-recent`.

## Data sources & terms
- **ClinicalTrials.gov API v2** (NLM/NIH): public, no key. Terms: clinicaltrials.gov/about-site/terms-conditions — data generally public domain; attribute NLM, don't imply endorsement, some records may reference third-party rights. No official numeric rate limit published; we throttle to ≤46 req/min and back off on 429.
- **openFDA** (`drug/drugsfda`, `drug/label`): terms open.fda.gov/terms (checked 2026-10-12 PT): data public domain / CC0 1.0 unless marked (commercial reuse OK); attribution requested ("Data provided by the U.S. Food and Drug Administration (https://open.fda.gov)"); no warranty; API responses say results are unvalidated, don't use for medical decisions. FDA may restrict abusive use. Limits without key: 240 req/min and **1,000 req/day per IP** (open.fda.gov/apis/authentication); with free key 120k/day (key not obtained — needs signup approval). We throttle to 1 req/s. One 4-company profile run ≈ 10 openFDA calls. Label PDFs/SPL text may contain third-party copyrighted material; we store metadata and links only.
- **NIH RePORTER API v2** (`api.reporter.nih.gov`, checked 2026-10-12 PT): public, no key. Policy on the API page: post **no more than 1 request/second**, run large jobs on weekends or weekdays 9 PM–5 AM ET, or NIH may block the IP. Max page size 500, max offset 14,999. Data is US federal government (NIH) award data. We throttle to 1 req/s.
- **PubMed via NCBI E-utilities** (`eutils.ncbi.nlm.nih.gov`; usage policy at ncbi.nlm.nih.gov/books/NBK25497, which blocked our fetcher today; numbers are from NCBI's long-published policy): no key → **max 3 req/s** (we space calls 0.4 s), with large jobs at off-peak times. NCBI asks clients to send `tool` and `email`. Neither needs registration, so we always send `tool=biocatalystfeed`. `email` is sent only if `NCBI_EMAIL` is set (unset by default so we don't volunteer anyone's address). An API key (10 req/s) needs an NCBI account, so we don't use one. NLM's disclaimer: PubMed citations are mostly public, but **abstracts can be under publisher copyright**, so we store titles, authors, journal, dates, DOI and PubMed links only, never abstracts.
- **bioRxiv / medRxiv API** (`api.biorxiv.org`, checked 2026-10-12 PT): public, no key, **no published rate limit** (we use 1 req/s). Each preprint has its own licence (CC-BY, CC-NC-ND, "no reuse", etc.), so we keep metadata and links only and drop the abstract after matching. The API has **no keyword or affiliation search**: we page a date window (30 records per call, so 7 days of both servers is about 60 calls and about 1 min) and filter locally. Affiliation matching uses the **corresponding author's institution only**.
- **SEC EDGAR** (secwatch): EDGAR data is public US-government information. Fair-access policy (sec.gov/os/accessing-edgar-data): **≤10 req/s total**, and a **declared User-Agent with organisation and contact email**. Default UA is `BioCatalystFeed/0.2 contact@biocat.ai` (set `BIOCATALYSTFEED_CONTACT` to your own contact, or override fully with `SEC_USER_AGENT`). We space calls 0.2 s (5 req/s). Endpoints: `efts.sec.gov/LATEST/search-index` (the JSON backend of the public EDGAR full-text search UI at sec.gov/edgar/search; it isn't separately documented as an "API", so treat it as subject to change; coverage is 2001+), `data.sec.gov/submissions/CIK##########.json` (documented), `www.sec.gov/files/company_tickers.json`, and filing documents under `/Archives/edgar/data/`.
- Not used: PatentsView. Its PatentSearch API is understood to require a registered API key (an account); not re-verified 2026-10-12 because the docs site returned HTTP 500. Deferred. Third-party PDUFA calendars are proprietary.

## grantwatch / paperwatch / secwatch: added 2026-10-12 PT
Shared plumbing is in `biowatch/` (throttled HTTP client and a generic SQLite snapshot/diff `ItemStore`). Tables are prefixed `grant_*`, `paper_*`, `sec_*`, so all three can share the trialwatch DB (default `biowatch.db`; MCP uses `TRIALWATCH_DB`).
```bash
grantwatch search --org "ELI LILLY AND COMPANY" --org-exact          # by org (wildcard unless --org-exact)
grantwatch search --pi "Ioannou" --since 2026-01-01                  # by PI + award notice date
grantwatch search --keyword '"resmetirom" OR "VK2735"' --fy 2026     # keyword in title/terms/abstract (OR -> any term)
grantwatch --db tw.db watch --name incretin --keyword '"tirzepatide" OR "retatrutide"'   # new_award, award_amount_change, project_end_date_change...
grantwatch --db tw.db changes --since 2026-10-01
paperwatch search --affiliation "Viking Therapeutics" --preprint-days 7
paperwatch search --drug resmetirom MGL-3196 --since 2026-09-01 --no-preprints
paperwatch search --keyword "obesity AND amylin" --since 2026-10-01
paperwatch --db tw.db watch --name mdgl --affiliation "Madrigal Pharmaceuticals" --since 2026-01-01   # new_paper; title/version/published_doi changes
secwatch pdufa MDGL --since 2023-01-01        # name, ticker or CIK; prints UNVERIFIED candidates (* = nearest to the mention)
secwatch --db tw.db watch --name sec-mdgl MDGL   # new_pdufa_filing / candidates_change
fdawatch profile Lilly Madrigal "Viking Therapeutics" --preprint-days 7 --md p.md --json   # full merged profile
fdawatch profile Lilly --basic                 # old trials + FDA only
```
- **grantwatch**: RePORTER `projects/search` takes org (wildcard or exact), PI (`any_name`), keyword (`advanced_text_search` over title, terms and abstract), award-notice date window and fiscal years. Records are keyed by `appl_id`, so each new fiscal-year award or supplement counts as a `new_award`. Tracked fields: award_amount, project_end_date, award_notice_date, fiscal_year, org_name, pis.
- **paperwatch**: PubMed query builder: affiliation → `"X"[ad]`, drug → `"X"[tiab] OR "X"[nm]`, keyword → raw PubMed syntax, `--since` → entry date (`edat`). Results are sorted by publication date, so epub-ahead items dated in the future come first. Preprints: whole-word, case-insensitive match on title + abstract (drug/keyword) and corresponding institution (affiliation). We keep the latest version per DOI.
- **secwatch (prototype)**: runs a full-text search for `"PDUFA"` in a company's 8-Ks (including EX-99 press releases), fetches each document, strips HTML, and pulls dates within 120 chars of "PDUFA" / "Prescription Drug User Fee Act" / "target action date" / "goal date". Date formats: `March 14, 2024`, `March 2024`, `Q1 2025`, `first quarter of 2025`, `second half 2025`, `3/14/2024`, and `March 14` without a year (year guessed from the filing date and marked `year_inferred`). The nearest date per mention is `best=True`. **Every candidate is labelled UNVERIFIED**, and dates may be past, superseded, or about a different product.
- **company_profile** (CLI `fdawatch profile`, MCP `company_profile`) adds `grants` (org grants via the alias `nih_orgs` + grants mentioning the alias `drugs`), `papers` (PubMed by affiliation, PubMed by key drugs, and preprints), `sec` (CIK, 8-K count, PDUFA mentions over the last 3 years), and `pdufa` (an UNVERIFIED candidate list, or a "none found" note). Each source is wrapped, so a failure shows up as `{"error": ...}` instead of breaking the profile. Pass `--basic` / `basic=True` for the old output.
- **Aliases extended** (`fdawatch/aliases.py`): `nih_orgs`, `pubmed_affil`, `preprint_affil`, `drugs`, `sec_cik` for all 8 companies. CIKs come from SEC company_tickers.json. Terns (acquired by Merck) and Zealand (not SEC-registered) have no CIK. Lilly is the only company with a RePORTER org record (`ELI LILLY AND COMPANY`: 7 old 2008–09 PSI subprojects).
- **New MCP tools**: `search_grants`, `snapshot_grants`, `grant_changes_since`, `search_papers`, `snapshot_papers`, `paper_changes_since`, `sec_pdufa_mentions`. `company_profile` gained `basic` and `preprint_days` (default 7; 0 skips preprints).
- **Samples (real data, 2026-10-12 PT)**: `samples/company_profiles_full.md|json` (Lilly, Madrigal, Viking; full run about 2 min, mostly bioRxiv paging). `samples/sample.db` adds baselines `grants-incretin-drugs` (60 grants), `papers-mdgl-vktx` (20), and `sec-mdgl` (3 filings, 2 runs).

## Known limits
- Diff is snapshot-based: changes are detected only between our own runs (no historical backfill; CT.gov version history not used).
- Sponsor search is free-text (`query.spons`): matches collaborators/similar names. Since 0.3.4 `trialwatch.core.search` expands known companies/tickers via `fdawatch/aliases.py` `ct_queries` (merged by NCT ID; a bare ticker is not sent itself); unknown names are sent as typed.
- Tracked fields: status, phase, enrollment, start/primary-completion/completion dates, sponsor, title, why_stopped, has_results, and (0.3.0) interventions, primary outcome measures, arm count, site count, results first posted. Site count needs `LocationFacility` in the CT.gov field list, which makes responses roughly 20x larger for big multi-site sponsors; still one page per 1,000 trials. Not tracked: secondary endpoints, eligibility, individual site names.
- No email/alert delivery, auth, billing, or multi-tenant storage.
- grantwatch: NIH-funded work only. Companies rarely hold NIH grants, so the useful company signal is grants mentioning their *drugs* (academic and competitor activity). Keyword matching is RePORTER's own and can return loosely related projects.
- paperwatch: affiliation strings are literal (`[ad]` misses variant spellings). Preprint affiliation covers the corresponding author only. Preprint windows longer than about 30 days are slow (bioRxiv posts about 150/day, 30 per call at 1 req/s). No full-text, citation, or retraction tracking.
- secwatch: finds only what companies furnish to the SEC as 8-Ks (Lilly and Viking had **zero** 8-K PDUFA mentions in 3 years, and big pharma rarely cites PDUFA dates). EFTS returns at most 100 hits per page, ranked by relevance (we sort by file date after fetching). Regex can mis-assign dates (e.g. an earnings dateline next to "PDUFA"). Not a PDUFA calendar.

## v0.2 changes (2026-10-12 PT, launch prep)
- **Branding**: package `biocatalystfeed` (v0.2.2; v0.3.0 adds `bcf ema` and `bcf adcom`), umbrella CLI `biocatalystfeed` / `bcf` (`bcf trials|fda|grants|papers|sec|ema|adcom|profile|mcp`), MCP entry `biocatalystfeed-mcp`; legacy commands kept. Licence Apache-2.0.
- **Exclusion + ranking** (`biowatch/filters.py`): `--exclude TERM…` (whole-word, case-insensitive, on title/conditions/interventions/org/PI/brand etc.) and `--rank` (title hit = 3, other field hit = 1, ties by date) on trials, fda approvals, grants, papers; MCP `exclude`/`rank` params. For `trialwatch watch`, exclusion filters the report/feed only; the snapshot keeps the full result.
- **Europe PMC** (`paperwatch.core.EuropePMCClient`, REST `webservices/rest/search`, no key, 0.5 s spacing, cursor paging): new papers source (`--sources pubmed europepmc preprints`). Query: `AFF:` for affiliation (any author, unlike the bioRxiv API's corresponding author only), `TITLE/ABSTRACT/CHEM` for drugs, raw syntax for keyword, `FIRST_PDATE` window. Europe PMC terms of use were not re-read today (europepmc.org/Copyright did not render for our fetcher): **verify before the paid launch**. Metadata and links only.
- **Fast preprints**: bioRxiv/medRxiv via Europe PMC `SRC:PPR AND PUBLISHER:"bioRxiv"/"medRxiv"` (1–2 calls instead of about 60 per week of window; Madrigal profile with 30-day preprints ran in about 4.5 s vs about 2 min before). Falls back to the bioRxiv API on error; `--rxiv-api` forces the old path. Europe PMC indexes preprints with some lag (often 1–2 days).
- **Cross-source dedup** by DOI (normalised, including a preprint's published DOI) and PMID, transitively; priority PubMed > Europe PMC > preprint servers; `sources` lists all.
- **grantwatch PI matching**: `"Jane A. Doe"` / `"Doe, Jane A"` → RePORTER `first_name`+`last_name` query, then a local filter: last and first names exact (a one-letter first name matches as an initial), and middle initials must agree when both are present. `--pi-exact` also rejects blank or different middles. A single token still uses `any_name`.
- **Grant sorting**: newest award notice first; awards dated after today are flagged `future_dated` (shown with `~`) and listed after current ones. `--no-future` drops them; `--sort fiscal_year|award_amount|relevance`.
- **secwatch**: companies with no CIK (private, non-US such as `ZEAL.CO`, acquired) now get a clear explanation instead of "no CIK"; the profile shows the same. SEC UA default `BioCatalystFeed/0.2 contact@biocat.ai`; set `BIOCATALYSTFEED_CONTACT` or `SEC_USER_AGENT`.
- **Digests**: every `watch` takes `--rss FILE` / `--json-feed FILE` (RSS 2.0 / JSON Feed 1.1, disclaimer included); `paperwatch changes` too; MCP `changes_feed(tool, since, watch, format)`. No email sending.
- **Apify actor**: self-contained. `scripts/sync_actor.py` vendors the packages into `actor/src`, the Dockerfile uses `actor/` as its context (`actor.json`: `dockerfile ../Dockerfile`, `dockerContextDir ..`), and `.dockerignore` is added. The input schema now gives every field a description, adds `excludeTerms` and a date `pattern`, and is validated by tests along with `input.json`. Docker isn't installed on the box, so the image build itself is untested.
- **Patents**: not added (PatentsView key requirement; see above).

## v0.3.0 (2026-10-21 PT)
- **Trial severity** (`trialwatch/severity.py`): `severity()` labels each change critical / notable / minor (rules in the
  README), computed when changes are read, so changes stored by older versions get labels too. `shift_days` for date fields
  (YYYY-MM dates count as the 1st of the month). `Store.changes(min_severity=...)`.
- **New trial fields**: `primary_outcomes` (measures joined with " | "), `arm_count`, `site_count`, `results_first_posted`.
  `diff_records` skips these when the stored snapshot predates them (`ADDED_0_3`).
- **adcomwatch** (Federal Register API, `https://www.federalregister.gov/api/v1/documents.json`, documented, no key,
  checked 2026-10-21 PT): query = FDA agency + NOTICE type + term "advisory committee" + publication-date window, 100 per
  page, up to 5 pages. Title rules keep meeting / amendment / postponement / cancellation notices. Area from the committee
  name (drugs, biologics, devices, tobacco, other). For meeting and amendment notices we fetch the full text
  (`raw_text_url`, 1 request each, 1 req/s) and parse the `Agenda:` paragraph (minus the standard webcast sentence), the
  DATES section (or "would be held on <date>" in amendments), NDA/BLA/sNDA numbers and "submitted by / from <sponsor>".
  Regex parsing can miss sponsors or dates; output says to check the notice and fda.gov. Store prefix `adcom`, key =
  FR document number.

## crlwatch (2026-10-26 PT)
- **Source**: openFDA `https://api.fda.gov/transparency/crl.json` (documented at open.fda.gov/apis/transparency/completeresponseletters,
  no key, same throttled `OpenFDAClient` as fdawatch; CC0 per open.fda.gov/license). 458 letters on 2026-10-26, newest
  2026-08-07, `last_updated` 2026-08-13 (FDA updates "infrequently", so CRLs appear with a lag).
- **Query**: server-side `letter_date` range, `company_name` phrase(s), `approval_status`, and `application_number:*<digits>*`
  (the field is an exact keyword with values like `BL 125827` or `BLA 761303/Original 1`, so phrase/number search misses).
  Keyword/topic/exclude filter locally over up to 1,000 letters. Sort `letter_date:desc`.
- **Parsing**: topics from all-caps section headings via `TOPIC_RULES` (boilerplate headings and signatory names ignored);
  excerpt = start of the first deficiency section; product = best-effort regex on the opening sentence (OCR, redactions).
- **Privacy**: `company_rep`, `approver_name`, `approver_title`, `company_address` are never copied. Store prefix `crl`,
  key = `file_name`; tracked `application_status`, `letter_type`. PDF link = `https://download.open.fda.gov/crl/<file_name>`.
- Hosted Cloudflare worker not updated (CLI + local MCP only).

## 0.3.4 (2026-10-28 PT, weekly review)
- **Sponsor aliases in trial search** (`trialwatch.core.sponsor_queries` / `raw_search`): fixes the daily routine's `sponsor:Terns Pharmaceuticals` watch returning 0 trials. CLI `--no-aliases`; `company_trials` passes `sponsor_aliases=False` (it already loops over `ct_queries`). Hosted worker has a small `CT_SPONSOR` map mirroring the table (Terns + tickers).
- **MCP schema quality** (`trialwatch/tooldocs.py`): Glama's Tool Definition Quality Score (scored 2026-10-23 UTC, 22 tools) was B 3.2/5, the recurring deduction being "0% schema description coverage" and "no annotations". All params now carry descriptions via `Annotated[..., Field(description=...)]` set on `__signature__` (works on mcp 1.x FastMCP and 2.x MCPServer); tools get `ToolAnnotations` by kind (read / local / snapshot). `tests/test_v034.py` fails if a new param lacks a description.

## 0.3.5 (2026-10-28 PT): FDA decision calendar (`decisionwatch`)
- Prompted by a competitor scan (DropwatchHQ "bio-catalyst" MCP: readouts + AdComs + approvals, source-anchored, x402-paid). See `samples/competitor_matrix.md`.
- **Sources / provenance**: pdufa = SEC EDGAR FTS `"PDUFA"` (+ `"drug"` / `"condition"` phrases) in 8-Ks filed in the last 365 days, reusing `secwatch.extract_candidates` (best candidate per mention) and `parse_when` for day/month/quarter/half; adcom = `adcomwatch.meetings` (Federal Register); approval = Drugs@FDA (`fdawatch.core.fda_approvals`, or a name search on `openfda.generic_name/brand_name`, `products.brand_name`, `products.active_ingredients.name` when only a drug is given), ORIG + efficacy supplements only; crl = `crlwatch.letters`. No third-party PDUFA calendars are used (ToS).
- **Confidence**: `company-disclosed` (pdufa), `scheduled` (adcom), `confirmed` (approval, crl). Every event has `provenance {source, field, method, retrieved}`; `retrieved` is dropped before snapshotting so it doesn't count as a change.
- **Keys**: pdufa `pdufa:<cik>:<drug|unknown>` (so a moved date shows as `date_change`), adcom `adcom:<FR doc number>`, approval `approval:<appl>:<type><num>`, crl `crl:<file_name>`. Tracked: `date`, `status`, `confidence`. Store prefix `fdadec`.
- **Known limits**: drug name near a PDUFA mention is best-effort (INN suffix / `Brand (generic)` regex); a filing mentioning several products under one company with no recognisable drug collapses to `unknown`. Condition filtering of approvals is coarse (pharmacologic class only). Device decisions (PMA/510k) not included.
- Hosted worker: lighter port (`fda_decisions`), max 10 8-K docs per call (subrequest budget); SEC requests use UA `BioCatalystFeed contact@biocat.ai` (the hosted UA format got HTTP 403 from efts.sec.gov).

## 0.3.6 (2026-10-28 PT): readout calendar, Trials at Risk, provenance, digests
- `readoutwatch/core.py`: CT.gov v2 `/studies` with `filter.advanced=AREA[PrimaryCompletionDate]RANGE[lo,hi] AND (phases) AND AREA[LeadSponsorClass]INDUSTRY`, `sort=PrimaryCompletionDate:asc`. Client throttle unchanged (≤46/min). Unknown tickers resolve via `decisionwatch.core.resolve_company` (SEC company_tickers.json).
- `readoutwatch/risk.py`: `stopped` uses `AREA[LastUpdatePostDate]` in the lookback window; `overdue` = active + primary completion in [today-lookback, yesterday] and still ESTIMATED. History flags read the `readout_*` tables (CT.gov API has no past values).
- `biowatch/provenance.py`: `stamp`/`enrich`/`check`/`ticker_match`. The hash excludes `verified_as_of`, `verify_hash`, `source_url`, `retrieved` and `ticker_*`. Snapshots drop `verified_as_of` so watches don't diff on time. `trialwatch.tooldocs.tool` wraps every MCP tool with `enrich`. The worker mirrors this (`stamp`/`enrich`/`tickerMatch`, `TICKER_ALIASES` generated from `fdawatch/aliases.py`; regenerate when aliases change).
- Site page: `bcf readouts page --upcoming 90 --max 1000 --out ../bcf-site/calendar` and commit. The page refreshes from the worker's `/calendar.json` (Cache API, 6 h), so the static snapshot is only a fallback. The site repo has no Actions workflow (see `ops/pages-workflow.yml.example`); a scheduled regenerate needs a token with `workflow` scope.
- Email: deliberately not implemented (no service signed up). See competitor_matrix.md "Remaining" for what a free option needs.
