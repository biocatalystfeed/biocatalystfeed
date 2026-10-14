<p><img src="assets/brand/logo-icon.svg" alt="BioCatalystFeed logo" width="64" height="64"></p>

# BioCatalystFeed

<!-- mcp-name: io.github.biocatalystfeed/biocatalystfeed -->

Website: https://biocat.ai · Contact: contact@biocat.ai

**An open-source catalyst feed for biotech: see what changed across clinical trials, FDA actions, NIH grants,
papers/preprints and SEC filings for the companies and drugs you follow.** Use it as a CLI, as an MCP server for AI
agents (Claude, Cursor, …), or as an Apify actor.

> ⚠️ **Not investment, legal or medical advice.** Data may be incomplete, delayed or wrong; PDUFA dates are unverified
> candidates from SEC filings. Always check the linked primary source.

## What it does
| Source | Command | What you get |
|---|---|---|
| ClinicalTrials.gov API v2 (NLM) | `bcf trials` | search, sponsor pipelines, **diffs**: new trials, status/phase/enrollment/date changes |
| openFDA (Drugs@FDA, SPL labels) | `bcf fda` | approvals (incl. novel NME/BLA flag), submissions, label revisions, diffs |
| NIH RePORTER | `bcf grants` | grants by org / PI (middle-initial aware) / keyword; new awards, amount changes |
| PubMed + **Europe PMC** + bioRxiv/medRxiv | `bcf papers` | papers & preprints, **deduplicated by DOI/PMID** across sources |
| SEC EDGAR | `bcf sec` | 8-K mentions of PDUFA dates (UNVERIFIED candidates, linked to the filing) |
| All of the above | `bcf profile` | one merged company profile (name or ticker) |

Across tools: `--exclude TERM …` to drop noise, `--rank` for relevance ordering, and `--rss` / `--json-feed` digest
files on every `watch` (local files you can serve or feed into any reader; nothing is emailed).

## Quickstart
```bash
pip install biocatalystfeed            # or: uvx biocatalystfeed --help
source .venv/bin/activate

bcf trials search --sponsor "Viking Therapeutics" --phase PHASE3
bcf papers search --drug resmetirom --since 2026-09-01 --exclude mice rat --rank
bcf grants search --pi "Ioannou, George N" --since 2024-01-01 --no-future
bcf sec pdufa MDGL --since 2023-01-01
bcf profile Lilly MDGL "Viking Therapeutics" --md profiles.md

# watches: first run = baseline, later runs report what changed (cron it daily)
bcf trials --db bcf.db watch --name obesity --condition obesity --phase PHASE3 --rss obesity.rss
bcf papers --db bcf.db watch --name mdgl --affiliation "Madrigal Pharmaceuticals" --json-feed mdgl.feed.json
```
The old commands (`trialwatch`, `fdawatch`, `grantwatch`, `paperwatch`, `secwatch`, `trialwatch-mcp`) still work.

### MCP server
```json
{"mcpServers": {"biocatalystfeed": {"command": "uvx", "args": ["biocatalystfeed", "mcp"],
  "env": {"BIOCATALYSTFEED_DB": "/path/to/bcf.db"}}}}
```
(or point `command` at an installed `biocatalystfeed-mcp`). Listed in the official MCP Registry as
`io.github.biocatalystfeed/biocatalystfeed`.
Tools include `search_trials`, `sponsor_pipeline`, `fda_approvals`, `company_profile`, `search_grants`,
`search_papers`, `sec_pdufa_mentions`, `snapshot_*` / `*_changes_since`, and `changes_feed` (RSS / JSON Feed).

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
Facts about DataLookout are from datalookout.com/citeline-alternative (checked 2026-10-12 PT). We have not tested
their product. Fuller, cited comparison: [`docs/COMPARISON.md`](docs/COMPARISON.md).

| | BioCatalystFeed (open source) | DataLookout |
|---|---|---|
| Price | Free (Apache-2.0); hosted tier planned | Free tier; Pro $49/month |
| Sources | ClinicalTrials.gov, openFDA, NIH RePORTER, PubMed, Europe PMC, bioRxiv/medRxiv, SEC EDGAR | ClinicalTrials.gov |
| Change tracking | Diffs between your own runs (trials: status, phase, enrollment, dates, sponsor, title, why stopped, results; plus FDA, grant, paper and SEC changes) | Daily scan; 13 fields incl. status, enrollment, primary endpoints, interventions, results, site counts, completion dates; changes marked Stopped/Notable/Minor |
| Delivery | CLI, MCP server for AI agents, RSS/JSON Feed files, Apify actor | Morning email digest + dashboard inbox |
| Watch limits | None when self-hosted | Free: 1 sponsor + 1 disease watchlist + 1 saved search; Pro: 10 of each |
| Scheduling | You run it (cron, Apify schedule) | Hosted, daily |
| Setup | Python install | "2 minutes" (their claim) |

Pick DataLookout for a hosted, emailed, ClinicalTrials.gov-only digest. Pick BioCatalystFeed if you want several
sources per company or ticker, agent/MCP access, or to self-host.

### Search filters (v0.2.1)
- `--exclude` takes words or phrases (space- or comma-separated); matching is whole-word and case-insensitive, and a
  trailing `*` is a prefix wildcard (`--exclude "murin*" rat`).
- `--rank` scores title hits 3 and other-field hits 1 (simple plurals tolerated), +1 for exact multi-word phrases in
  the title and +2 when every query term matches; ties break by newest date. The score is in `relevance`.

## Data sources, limits and etiquette
Built-in throttles follow each source's published policy (e.g. NIH RePORTER 1 req/s, NCBI ≤3 req/s without key, SEC
≤10 req/s with a declared User-Agent, openFDA 1,000 req/day per IP without key). We store **metadata and links only**
for papers/preprints, never abstracts. Change detection only covers your own runs; there's no historical backfill.
PDUFA dates are regex extractions from 8-K text, not a calendar. Attributions are in [`NOTICE`](NOTICE). Design notes
and per-source terms are in [`docs/DEVELOPER-NOTES.md`](docs/DEVELOPER-NOTES.md).

## Hosted tier
A paid hosted version (scheduled watches, persisted history, hosted MCP) is planned. Draft terms:
[`TERMS.md`](TERMS.md), [`PRIVACY.md`](PRIVACY.md) (drafts, not legal advice, not in effect).

## Contributing & licence
See [`CONTRIBUTING.md`](CONTRIBUTING.md), [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) and [`SECURITY.md`](SECURITY.md) (report vulnerabilities privately). Licensed under the [Apache License 2.0](LICENSE). BioCatalystFeed is
independent and not endorsed by NLM, NIH, FDA, SEC, EMBL-EBI/Europe PMC, or bioRxiv/medRxiv.
