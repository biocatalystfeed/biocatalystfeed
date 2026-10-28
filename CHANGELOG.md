# Changelog

## 0.4.0 — 2026-10-28
- **Licence change:** 0.4.0 and later is under the **Business Source License 1.1**. Licensor: BioCatalystFeed. The Additional Use Grant allows any production use except a Competing Offering. The Change Date is 12 months after each release, and the Change License is Apache-2.0. **0.3.6 and earlier remain Apache-2.0** (text in `LICENSES/Apache-2.0.txt`). See `NOTICE`.
- Hosted Worker: **free daily limit of 200 tool calls per IP per UTC day**, on top of the existing 30 requests/minute. `initialize`, `tools/list` and rejected calls are not counted, and the limit resets at 00:00 UTC. Over the limit, the Worker returns HTTP 429 with JSON-RPC error `-32002`, `Retry-After`, and `x-daily-limit` / `x-daily-remaining` / `x-daily-reset` headers, which CORS exposes. `GET /calendar.json` is not metered. Placeholder for future API keys (`x-api-key` / `Authorization: Bearer`): the key store is off, so any key gets a 401 "not enabled yet". Self-hosting has no limits: `pip install biocatalystfeed`.

## 0.3.6 — 2026-10-28
- New: market-wide **trial readout calendar** (`bcf readouts search|watch|changes|page` / `readoutwatch`). Upcoming ClinicalTrials.gov primary completion dates (`readout_date`, `readout_date_type` ESTIMATED / ACTUAL, `date_precision`), soonest first. Defaults: active, industry-sponsored Phase 2/3, next 90 days. Filters: `--sponsor` (name or ticker; alias table, then SEC's ticker list), `--condition`, `--intervention`, `--phases` (`any`), `--since/--until`, `--upcoming DAYS`, `--all-sponsors`, `--ticker-only`. Watches (prefix `readout`) report `new_readout`, `readout_date_change` (with `direction` delayed / pulled_in), `readout_date_type_change`, `status_change`, `enrollment_change`, `phase_change`.
- New: **Trials at Risk** (`bcf readouts at-risk`, MCP `trials_at_risk`): flags `stopped` (suspended / terminated / withdrawn, with why_stopped), `overdue`, `stale_overdue`, and from local snapshot history `delayed`, `enrollment_shortfall` and `enrollment_cut`; `risk_score` = sum of severities.
- New: **provenance on every record**: `verified_as_of`, `verify_hash` (sha256 of canonical JSON; `biowatch.provenance.check`), `source_url`, and `ticker` / `ticker_confidence` / `ticker_method` for company → ticker matching (`biowatch/provenance.py`). Applied to all MCP tool results (stdio + hosted), readouts, FDA decisions and trial search.
- New: **rendered digests**: `biowatch.digest.markdown` / `html` (email-ready inline styles; nothing is sent); `--digest-md` / `--digest-html` on every `watch` command; `--md/--html/--rss/--json-feed` on `bcf readouts search|at-risk`; `changes_feed(format='markdown'|'html')`; `changes_feed` accepts `readouts`.
- New: **public calendar page** at biocat.ai/calendar/ (`bcf readouts page --out DIR`): static HTML + `calendar.json` with client-side filters (sponsor/ticker, condition, phase, ticker-only); on load it switches to the hosted Worker's cached `GET /calendar.json` (6 h edge cache; alias-table tickers only) when the static snapshot is more than a day old.
- MCP: `readout_calendar`, `snapshot_readouts`, `readout_changes_since`, `trials_at_risk` (all parameters described, annotations set); 32 stdio tools.
- Hosted Worker: `readout_calendar` and `trials_at_risk` tools (9 total), provenance + ticker confidence on every record, `GET /calendar.json`; serverInfo 0.3.6.
- Trial records gain `primary_completion_type` (CT.gov `PrimaryCompletionDateType`).
- Docs: README, `docs/COMPARISON.md` and `samples/competitor_matrix.md` updated (parity status, remaining gaps, what a free email option needs).

## 0.3.5 — 2026-10-28
- New: FDA decision calendar + watch (`bcf fda-decisions search|watch|changes` / `decisionwatch`). One list of FDA decision events, upcoming soonest first, then past newest first:
  - `pdufa`: upcoming PDUFA / target action dates **disclosed by companies in SEC 8-K filings** (EDGAR full-text search). FDA does not publish PDUFA dates, so these carry `confidence: "company-disclosed"` and the provenance method "regex extraction (UNVERIFIED)", plus the filing link, filing date and the text around the date. Day / month / quarter / half precision (`date_precision`). The newest filing wins per company + drug.
  - `adcom`: FDA advisory committee meetings from Federal Register notices (`confidence: "scheduled"`; status scheduled / postponed / cancelled / held).
  - `approval`: original approvals and efficacy supplements from Drugs@FDA (`confirmed`); searched by drug name when `--drug` is given.
  - `crl`: complete response letters from openFDA (`confirmed`, published with a lag).
  - Filters: `--drug`, `--company` (name or ticker; alias table, then SEC's ticker list), `--condition`, `--kinds`, `--since/--until`, `--upcoming DAYS`. One failing source is reported in `errors` and does not hide the others.
  - Watches (same snapshot store as the other tools, prefix `fdadec`) report `new_decision_event`, `date_change` (e.g. a PDUFA date moved by a later 8-K, an AdCom rescheduled), `status_change` (pending -> date_passed, scheduled -> postponed/cancelled, CRL -> approved_since) and `confidence_change`; `--rss` / `--json-feed` digests for notifications.
  - MCP: `fda_decisions`, `snapshot_fda_decisions`, `fda_decision_changes_since` (all parameters described, annotations set); `changes_feed` accepts `fda-decisions`.
- Hosted Worker: `fda_decisions` tool (read-only; pdufa / adcom / approval / crl with confidence + provenance); README now lists all 7 hosted tools; SEC requests use SEC's "Company email" User-Agent format; serverInfo 0.3.5.
- Docs: `samples/competitor_matrix.md` (BCF vs DropwatchHQ Bio Catalyst vs DataLookout, with remaining gaps); `docs/COMPARISON.md` updated.

## 0.3.4 — 2026-10-28
- Fix: trial searches by sponsor now resolve known company names and tickers to the names ClinicalTrials.gov uses. `bcf trials search|watch|pipeline --sponsor "Terns Pharmaceuticals"` (or `TERN`) previously returned 0 trials because CT.gov lists the sponsor as "Terns, Inc., a subsidiary of Merck & Co., Inc."; it now finds them. Queries for each alias are merged by NCT ID; a bare ticker is not sent as free text (it matched unrelated companies). Unknown names are sent as typed. `--no-aliases` restores exact behaviour. Applies to MCP `search_trials`, `snapshot_watch` and `sponsor_pipeline`, and the hosted `search_trials`.
- MCP tool metadata: every parameter of all 25 stdio tools now has a JSON-schema description (was 0%), and every tool carries MCP annotations: search/get tools `readOnlyHint` + `openWorldHint`; `*_changes_since` / `changes_feed` read the local DB only (`openWorldHint: false`); `snapshot_*` append to the local DB (not read-only, not destructive). Descriptions of the change/snapshot tools now say when to use which. Hosted endpoint: parameter descriptions for all 6 tools; serverInfo 0.3.4.

## 0.3.3 — 2026-10-26
- New source: FDA complete response letters (CRLs) from openFDA's transparency endpoint (`bcf crl search|watch|changes` / `crlwatch`; MCP tools `fda_complete_response_letters`, `snapshot_crl`, `crl_changes_since`; `changes_feed` accepts `crl`). Filters: company, application number, letter-date window, application status (Approved since / Unapproved), keyword (drug or any word in the letter), deficiency topic. Each record has a best-effort product name, deficiency topics from the letter's section headings, an excerpt of the first deficiency and the FDA PDF link. Watches report new letters and Unapproved → Approved flips. Personal fields in the source (company representative, signatory, address) are not copied. openFDA data is public domain / CC0. Also on the hosted endpoint as `fda_complete_response_letters` (read-only search; same rate limits, no logs).
- Hosted Worker: `fda_complete_response_letters` tool (openFDA CRL data, public domain); serverInfo 0.3.3.
- Worker dev dependency: wrangler 4.153.0 (resolves undici advisories in the miniflare chain; dev/deploy tooling only, not shipped in the Worker bundle).

## 0.3.2 — 2026-10-26
- Opt-in Global coverage (off by default; default outputs unchanged): links to records in non-FDA/EMA registries (e.g. ChiCTR, other WHO-listed national registries) plus paper jurisdiction flags. `--global` / `--global-sources` on `bcf trials search` and `bcf papers search`; `include_global` / `global_sources` on MCP `search_trials` and `search_papers` (stdio and hosted).
  - Trials: labelled link-outs (`registry_class: "non-FDA/EMA registry"`, `registry`, `jurisdiction`, `source_url`, `also_registered_as`) for ChiCTR, CTRI, jRCT/JPRN, CRIS, ANZCTR, ReBEC, PACTR, IRCT, TCTR and ISRCTN IDs found in ClinicalTrials.gov secondary IDs. Link only: no foreign registry data is fetched, scraped or stored. WHO ICTRP data, ChiCTR pages and the NMPA/CDE platform are not ingested.
  - Papers: `jurisdiction_flag` ("non-FDA/EMA oversight" / "unknown") and `jurisdiction` from Europe PMC author-affiliation countries; never guessed.
  - Text output prefixes labels and prints the standard disclaimer once; JSON adds `global_disclaimer`; RSS/JSON Feed items with `registry_class` get the label prefix and disclaimer.
  - One-line stderr tip on searches without `--global` (TTY only; off with `--quiet`, `--json` or `BCF_NO_TIPS=1`); `bcf --global --help` detail text; docs/GLOBAL.md.

## 0.3.1 — 2026-10-21
- PubMed `--since`/`--until` now filter on the publication date that is displayed (esearch uses `pdat`, plus an exact local filter on the shown date); previously the filter used Entrez date (`edat`), so older-looking papers could appear. Test added.
- openFDA: per-request timeouts (3 s connect / 6 s read), at most 2 retries with short capped backoff, and a 15 s total budget, so an openFDA outage fails in about 15 s instead of minutes. Tests added.
- `bcf trials changes` prints a readable summary by default; `--json` gives the previous JSON-lines output.
- README: venv-first Quickstart (macOS PEP 668), `uvx`/`pipx` options, note that `--db` goes after the tool name, and a Contributing/Testing section (`pip install -e '.[dev]'`, `pytest`, `TRIALWATCH_LIVE=1`).

## 0.3.0 — 2026-10-21
- New source: FDA advisory committee meetings from the Federal Register API (`bcf adcom search|upcoming|watch|changes` / `adcomwatch`; MCP tools `fda_adcom_meetings`, `snapshot_adcom`, `adcom_changes_since`; `changes_feed` accepts `adcom`). Parses committee, meeting date, kind (meeting / amendment / postponement / cancellation), and NDA/BLA numbers and sponsors from each notice's agenda. Federal Register documents are U.S. government works (public domain).
- ClinicalTrials.gov diffs now also track primary endpoints, arm count, interventions, site count and results-first-posted date. Snapshots from older versions start tracking the new fields on their next run (no false "changes" on upgrade).
- Every trial change has a `severity` (critical / notable / minor) and date changes have `shift_days`; `--min-severity` on `bcf trials watch` / `changes`, `min_severity` on MCP `trial_changes_since`; markdown reports sort critical first and RSS/JSON Feed titles show the severity.
- New source: European Medicines Agency (EMA) medicines data (`bcf ema` / `emawatch`, MCP tools `ema_medicines`, `snapshot_ema`, `ema_changes_since`; `changes_feed` accepts `ema`). Tracks CHMP opinions, EC decisions, refusals, withdrawals and suspensions from EMA's official daily JSON export; every record carries EMA source attribution as EMA's reuse terms require.
- Primary website is now https://biocat.ai; project contact and SEC User-Agent default contact are now `contact@biocat.ai`.

## 0.2.2 — 2026-10-14
- SEC User-Agent default contact is now `contact@biocatalystfeed.com` (was a `.invalid` placeholder).
- Optional `OPENFDA_API_KEY` and `NCBI_API_KEY` environment variables are now read and documented in the README.
- Launch hardening: jittered backoff, `Retry-After` support and network-error retries; NCT ID validation; MCP input clamps; friendly CLI errors.
- Added SECURITY.md, CODE_OF_CONDUCT.md, issue/PR templates, gitleaks config.

## 0.2.1
- Search filters (exclude wildcards/comma lists), better relevance ranking, Europe PMC keywords.
- MCP Registry `server.json`, `glama.json`, COMPARISON.md, TERMS/PRIVACY.

## 0.2.0
- Initial open-source release.
