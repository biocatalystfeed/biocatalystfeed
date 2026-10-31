<p><img src="assets/brand/logo-icon.svg" alt="BioCatalystFeed logo" width="64" height="64"></p>

# BioCatalystFeed

<!-- mcp-name: io.github.biocatalystfeed/biocatalystfeed -->

Website: https://biocat.ai · Contact: contact@biocat.ai

**An open-source catalyst feed for biotech: see what changed across clinical trials, FDA and EMA actions, NIH grants,
papers/preprints and SEC filings for the companies and drugs you follow.** Use it as a CLI, as an MCP server for AI
agents (Claude, Cursor, …), or as an [Apify actor](https://apify.com/biocatalystfeed/biocatalystfeed-clinicaltrials-monitor).

> ⚠️ **Not investment, legal or medical advice.** Data may be incomplete, delayed or wrong; PDUFA dates are unverified
> candidates from SEC filings. Always check the linked primary source.

## What it does
| Source | Command | What you get |
|---|---|---|
| ClinicalTrials.gov API v2 (NLM) | `bcf trials` | search, sponsor pipelines, **diffs**: new trials, status/phase/enrollment/date, primary-endpoint, arm, intervention, site-count and results-posted changes, each labelled **critical / notable / minor** |
| openFDA (Drugs@FDA, SPL labels) | `bcf fda` | approvals (incl. novel NME/BLA flag), submissions, label revisions, diffs |
| NIH RePORTER | `bcf grants` | grants by org / PI (middle-initial aware) / keyword; new awards, amount changes |
| PubMed + **Europe PMC** + bioRxiv/medRxiv | `bcf papers` | papers & preprints, **deduplicated by DOI/PMID** across sources |
| SEC EDGAR | `bcf sec` | 8-K mentions of PDUFA dates (UNVERIFIED candidates, linked to the filing) |
| European Medicines Agency (EMA) | `bcf ema` | EU centrally authorised medicines: CHMP opinions, EC authorisations, refusals, withdrawals, suspensions; orphan/PRIME flags; diffs |
| Federal Register (FDA notices) | `bcf adcom` | FDA advisory committee meetings: committee, meeting date, NDA/BLA numbers and sponsors from the agenda; postponements/cancellations; diffs |
| openFDA complete response letters (FDA) | `bcf crl` | FDA complete response letters (CRLs) for NDAs/BLAs: company, application, product, deficiency topics (facility, product quality, clinical, safety ...), first-deficiency excerpt, PDF link; diffs flag new letters and Unapproved → Approved |
| **FDA decision calendar** (SEC EDGAR 8-Ks + Federal Register + Drugs@FDA + openFDA CRLs) | `bcf fda-decisions` | one list of upcoming **PDUFA dates** (company-disclosed in 8-Ks), **AdCom meetings**, recent **approvals** and **CRLs**; filter by drug, company/ticker, condition, kind, date window or `--upcoming DAYS`; every event has `confidence` (company-disclosed / scheduled / confirmed), `date_precision` and `provenance`; **watches notify** on new events, moved PDUFA dates, postponed AdComs and status flips |
| **Trial readout calendar** + **Trials at Risk** (ClinicalTrials.gov) | `bcf readouts` | market-wide upcoming **primary completion dates** (ESTIMATED / ACTUAL), filter by sponsor/ticker, condition, intervention, phase, window, industry-only, ticker-only; watches report new readouts and **slipped dates**; `at-risk` flags stopped, overdue, delayed and enrollment-shortfall trials with a risk score; Markdown / HTML / RSS / JSON digests; static page `bcf readouts page` (live at [biocat.ai/calendar](https://biocat.ai/calendar/)) |
| All of the above | `bcf profile` | one merged company profile (name or ticker) |

**Optional global coverage (`--global` / `include_global`).** Off by default. When you turn it on, BCF also links to records in trial registries outside the US and EU, such as China's ChiCTR and other WHO-listed national registries, and flags papers from other jurisdictions. These records may come from research run under regulatory, ethics and data standards different from, and sometimes lighter than, those of the US or EU. They are labelled "non-FDA/EMA registry". The option is for users who want to see everything that is out there. Inclusion is not an endorsement or recommendation and is not medical, legal or investment advice.

Records are links (registry ID + URL, from ClinicalTrials.gov secondary IDs); papers get `jurisdiction_flag` from author-affiliation countries (`"unknown"` when none is found). Details: `bcf --global --help` or [docs/GLOBAL.md](docs/GLOBAL.md).

Across tools: `--exclude TERM …` to drop noise, `--rank` for relevance ordering, and `--rss` / `--json-feed` digest
files on every `watch` (local files you can serve or feed into any reader; nothing is emailed).

## Quickstart
```bash
python3 -m venv .venv && source .venv/bin/activate   # macOS/Homebrew Python blocks global pip installs (PEP 668)
pip install biocatalystfeed
# no venv needed:  uvx --from biocatalystfeed bcf --help    or    pipx install biocatalystfeed

bcf trials search --sponsor "Viking Therapeutics" --phase PHASE3
bcf trials search --sponsor TERN                           # known names/tickers are alias-resolved (CT.gov: "Terns, Inc."); --no-aliases to send as typed
bcf papers search --drug resmetirom --since 2026-09-01 --exclude mice rat --rank
bcf grants search --pi "Ioannou, George N" --since 2024-01-01 --no-future
bcf sec pdufa MDGL --since 2023-01-01
bcf profile Lilly MDGL "Viking Therapeutics" --md profiles.md
bcf ema search --status Opinion --since 2026-09-01          # latest CHMP opinions (EU)
bcf adcom upcoming --area drugs biologics                   # scheduled FDA advisory committee meetings
bcf crl search --since 2026-01-01 --status Unapproved       # FDA complete response letters, newest first
bcf fda-decisions search --upcoming 90                     # PDUFA dates (8-K) + AdComs in the next 90 days, soonest first
bcf fda-decisions search --company BBIO                     # all FDA decision events for a ticker (pdufa, adcom, approval, crl)
bcf fda-decisions search --drug semaglutide --kinds approval crl --since 2025-01-01
bcf readouts search --upcoming 60 --condition obesity          # industry Ph2/3 primary completions in the next 60 days
bcf readouts search --sponsor VKTX --upcoming 720 --md vktx.md  # one company's readouts + a Markdown digest
bcf readouts at-risk --condition NASH --html risk.html          # Trials at Risk (stopped / overdue / delayed / enrollment shortfall)

# watches: first run = baseline, later runs report what changed (cron it daily)
bcf trials --db bcf.db watch --name obesity --condition obesity --phase PHASE3 --rss obesity.rss
bcf trials --db bcf.db changes --name obesity --min-severity critical   # terminations, endpoint rewrites
bcf readouts --db bcf.db watch --name ph3-90d --phases PHASE3 --upcoming 90 --digest-html readouts.html --json-feed readouts.feed.json   # notify: new readouts, date slips, ESTIMATED->ACTUAL
bcf fda-decisions --db bcf.db watch --name obesity-fda --condition obesity --json-feed fda.feed.json   # notify: new/moved PDUFA dates, AdComs, approvals, CRLs
bcf papers --db bcf.db watch --name mdgl --affiliation "Madrigal Pharmaceuticals" --json-feed mdgl.feed.json
```
Global flags such as `--db` go **after the tool name and before the subcommand**: `bcf trials --db bcf.db changes`, not `bcf --db bcf.db trials changes` or `bcf trials changes --db bcf.db`.
`bcf trials changes` prints a readable one-line-per-change summary; add `--json` for one JSON object per line.
PubMed `--since`/`--until` filter on the publication date shown in the output (Europe PMC uses first-publication date).

The old commands (`trialwatch`, `fdawatch`, `grantwatch`, `paperwatch`, `secwatch`, `trialwatch-mcp`) still work.

### MCP server
```json
{"mcpServers": {"biocatalystfeed": {"command": "uvx", "args": ["biocatalystfeed", "mcp"],
  "env": {"BIOCATALYSTFEED_DB": "/path/to/bcf.db"}}}}
```
(or point `command` at an installed `biocatalystfeed-mcp`). Listed in the official MCP Registry as
`io.github.biocatalystfeed/biocatalystfeed`.
Tools include `search_trials`, `sponsor_pipeline`, `fda_approvals`, `company_profile`, `search_grants`,
`search_papers`, `sec_pdufa_mentions`, `ema_medicines`, `fda_adcom_meetings`, `fda_complete_response_letters`, `fda_decisions` (FDA decision calendar), `readout_calendar` (trial readout calendar), `trials_at_risk`, `snapshot_*` (incl. `snapshot_fda_decisions`, `snapshot_readouts`) / `*_changes_since`, and `changes_feed` (RSS / JSON Feed / Markdown / HTML).

**Provenance on every record (0.3.6).** Every record returned by every MCP tool (stdio and hosted), and by `bcf readouts`
/ `bcf fda-decisions` / `bcf trials search`, carries `verified_as_of` (UTC), `source_url` (the official record or API URL),
`verify_hash` (`sha256:` of the record's canonical JSON, excluding the provenance and ticker fields; re-check with
`biowatch.provenance.check(record)`), and, where a company is named, `ticker`, `ticker_confidence` (1.0 source-given,
0.95 alias table, 0.9 SEC exact name, 0.6 SEC name prefix, 0 none) and `ticker_method`.

### Configuration
| Env var | Purpose |
|---|---|
| `BIOCATALYSTFEED_CONTACT` | contact email put in the SEC User-Agent (SEC fair-access policy). Default is the project contact (`contact@biocat.ai`); set it to your own contact for heavy SEC use |
| `SEC_USER_AGENT` | full SEC User-Agent override |
| `NCBI_EMAIL` | optional email sent to NCBI E-utilities |
| `OPENFDA_API_KEY` | optional openFDA API key (free at open.fda.gov/apis/authentication); raises daily/minute rate limits. Never logged |
| `NCBI_API_KEY` | optional NCBI E-utilities API key (free from your NCBI account settings); raises the PubMed limit from 3 to 10 req/s. Never logged |
| `BIOCATALYSTFEED_DB` (or `TRIALWATCH_DB`) | SQLite DB for the MCP server |
| `FDAWATCH_ALIASES` | JSON file extending the company alias table |

## How it compares
Facts about DataLookout are from datalookout.com, its /citeline-alternative and /clinical-trial-monitoring pages (checked 2026-10-21 PT). We have not tested
their product. Fuller, cited comparison: [`docs/COMPARISON.md`](docs/COMPARISON.md); three-way matrix incl. DropwatchHQ Bio Catalyst: [`samples/competitor_matrix.md`](samples/competitor_matrix.md).

| | BioCatalystFeed (open source) | DataLookout |
|---|---|---|
| Price | Free to self-host (BSL 1.1 from 0.4.0; 0.3.6 and earlier Apache-2.0); free hosted MCP endpoint (200 tool calls/day) | Free tier; Pro $49/month |
| Sources | ClinicalTrials.gov, openFDA (approvals, labels, CRLs), NIH RePORTER, PubMed, Europe PMC, bioRxiv/medRxiv, SEC EDGAR (PDUFA dates), EMA, Federal Register (FDA AdComs) | ClinicalTrials.gov |
| Change tracking | Diffs between your own runs (trials: status, phase, enrollment, dates, sponsor, title, why stopped, primary endpoints, arms, interventions, site counts, results posting; severity critical/notable/minor; plus FDA, EMA, AdCom, grant, paper and SEC changes) | Daily scan; 13 fields incl. status, enrollment, primary endpoints, interventions, results, site counts, completion dates; changes marked Stopped/Notable/Minor |
| Delivery | CLI, MCP server for AI agents (local, or hosted read-only subset), RSS/JSON Feed files, Apify actor | Morning email digest + dashboard inbox |
| Watch limits | None when self-hosted | Free: 1 sponsor + 1 disease watchlist + 1 saved search; Pro: 10 of each |
| Scheduling | You run it (cron, Apify schedule) | Hosted, daily |
| Setup | Python install | "2 minutes" (their claim) |

Pick DataLookout for a hosted, emailed, ClinicalTrials.gov-only digest. Pick BioCatalystFeed if you want several
sources per company or ticker, agent/MCP access, or to self-host.

### Trial change severity (v0.3.0)
Every trial change carries `severity`, and date changes carry `shift_days`:
- **critical**: status moves to TERMINATED / SUSPENDED / WITHDRAWN, a why-stopped reason appears, or the primary
  endpoint(s) are rewritten.
- **notable**: other status or phase changes, new trials, lead-sponsor changes, results posted, arm or intervention
  changes, enrollment changes of 20% or more, start / primary completion / completion dates moved 30+ days.
- **minor**: everything else (small date or enrollment tweaks, site-count changes, title edits).

Filter with `--min-severity notable|critical` on `bcf trials watch` / `changes`, or `min_severity` in the MCP tool
`trial_changes_since`. Snapshots made by older versions start tracking the new fields on their next run, so upgrading
doesn't produce a burst of false changes.

### Search filters (v0.2.1)
- `--exclude` takes words or phrases (space- or comma-separated); matching is whole-word and case-insensitive, and a
  trailing `*` is a prefix wildcard (`--exclude "murin*" rat`).
- `--rank` scores title hits 3 and other-field hits 1 (simple plurals tolerated), +1 for exact multi-word phrases in
  the title and +2 when every query term matches; ties break by newest date. The score is in `relevance`.

## Data sources, limits and etiquette
Built-in throttles follow each source's published policy (e.g. NIH RePORTER 1 req/s, NCBI ≤3 req/s without key, SEC
≤10 req/s with a declared User-Agent, openFDA 1,000 req/day per IP without key). We store **metadata and links only**
for papers/preprints, never abstracts. Change detection only covers your own runs; there's no historical backfill.
PDUFA dates are regex extractions from company 8-K text (FDA does not publish PDUFA dates); `bcf fda-decisions` labels them `confidence: company-disclosed` with the filing link, and always read the filing. Data provided by the U.S. Food and Drug Administration (https://open.fda.gov). Source: European Medicines Agency
(EMA), https://www.ema.europa.eu. Full attributions are in [`NOTICE`](NOTICE). Design notes
and per-source terms are in [`docs/DEVELOPER-NOTES.md`](docs/DEVELOPER-NOTES.md).

## Hosted MCP endpoint (free)
A free, read-only, rate-limited MCP endpoint (Streamable HTTP, no account) runs on Cloudflare Workers:

    https://bcf-mcp.lively-recipe-5a12.workers.dev/mcp

```json
{"mcpServers": {"biocatalystfeed-hosted": {"type": "http", "url": "https://bcf-mcp.lively-recipe-5a12.workers.dev/mcp"}}}
```
It offers 10 tools (`search_trials`, `get_trial`, `fda_approvals`, `search_papers`, `fda_complete_response_letters`,
`fda_decisions`, `readout_calendar`, `trials_at_risk`, `fda_adcom_meetings`, and the hosted-only **`paper_retraction_check`**), all with provenance fields, plus a cached
public `GET /calendar.json` (90-day readout calendar, refreshed every 6 h; feeds biocat.ai/calendar) over ClinicalTrials.gov, openFDA, PubMed, SEC EDGAR and the Federal Register. **Free tier:** 200 tool calls per IP per UTC day (resets at 00:00 UTC) and 30 requests/minute. `initialize` and `tools/list` don't count. Over the limit you get HTTP 429 with JSON-RPC error `-32002`, `Retry-After` and `x-daily-*` headers. `/calendar.json` is unmetered. API keys for higher limits are planned but not yet available. **Self-hosting is free and unlimited:** `pip install biocatalystfeed`.
**Retraction warning (hosted only, free):** `paper_retraction_check` takes up to 50 PMIDs or DOIs and reports, per paper, whether it is retracted, partially retracted, under an expression of concern or corrected, with links to each notice, the first notice date and how many sources agree (PubMed, Crossref including Retraction Watch records, OpenAlex). An OpenAlex-only signal is shown as `possible_retraction` with no warning. `none_found` means no notice was found, not that a paper is sound. One call counts as one tool call toward the free daily limit. Informational only; not medical or investment advice. Data: PubMed/MEDLINE (U.S. National Library of Medicine), Crossref metadata including the Retraction Watch Database (The Center for Scientific Integrity, openly available via Crossref), OpenAlex (CC0). This tool is not part of the source-available package.
Watches, change history and the other sources need the local install above. No request logs are kept; see
[`TERMS.md`](TERMS.md) and [`PRIVACY.md`](PRIVACY.md). Source: [`worker/`](worker/).

## Contributing / Testing
```bash
git clone https://github.com/biocatalystfeed/biocatalystfeed && cd biocatalystfeed
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest                      # offline tests; live-API tests are skipped by default
TRIALWATCH_LIVE=1 pytest    # also run tests that call the real public APIs (needs network; slower)
```

## Contributing & licence
See [`CONTRIBUTING.md`](CONTRIBUTING.md), [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) and [`SECURITY.md`](SECURITY.md) (report vulnerabilities privately). **Licence:** version 0.4.0 and later is under the [Business Source License 1.1](LICENSE). You can use, modify and self-host it for any purpose, including commercial internal use, but you cannot offer it to others as a competing catalyst, trial, FDA data, alert, API or MCP service. Each version becomes Apache-2.0 twelve months after its release. **Versions 0.3.6 and earlier stay [Apache-2.0](LICENSES/Apache-2.0.txt).** See [NOTICE](NOTICE). For commercial licensing, contact contact@biocat.ai. BioCatalystFeed is
independent and not endorsed by NLM, NIH, FDA, SEC, EMA, the Office of the Federal Register, EMBL-EBI/Europe PMC, or bioRxiv/medRxiv.
