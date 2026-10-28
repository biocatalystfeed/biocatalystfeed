# BioCatalystFeed vs DataLookout: coverage comparison

Checked 2026-10-14 (PT), updated 2026-10-21 and 2026-10-28 (PT). A three-way matrix including DropwatchHQ Bio Catalyst is in [`samples/competitor_matrix.md`](../samples/competitor_matrix.md). DataLookout facts come only from its public pages [1] and [3].
BioCatalystFeed facts come from this repository (v0.3.0). We have **not** used DataLookout's product; anything its public page doesn't state is
marked **unknown**. Corrections welcome via a GitHub issue.

The two tools overlap only on ClinicalTrials.gov change monitoring. DataLookout is a hosted, emailed product.
BioCatalystFeed is open-source software you run yourself (CLI, MCP server, Apify actor).

| | BioCatalystFeed | DataLookout | DataLookout source |
|---|---|---|---|
| Delivery model | Self-hosted Python package (PyPI), MCP server, Apify actor | Hosted web app + email | [1] |
| Price | Free to self-host (BSL 1.1 from 0.4.0; earlier Apache-2.0); hosted free tier 200 tool calls/day (Apify runs use your own Apify plan/credits) | Free tier; Pro $49/month or $490/year, cancel anytime | [1] |
| ClinicalTrials.gov | Yes (API v2): search, sponsor pipeline, diffs between your runs | Yes: daily snapshot + diff | [1] |
| Trial fields diffed | Status, phase, enrollment, start / primary completion / completion dates, lead sponsor, title, why-stopped, has-results, results first posted, primary endpoints, arm count, interventions, site count | 13 fields: overall status, why stopped, phase, primary endpoints, enrollment, lead sponsor, site count, primary completion date, completion date, arm count, interventions, results posting date, start date | [3] |
| Change severity labels | Yes: critical / notable / minor, plus date shift in days (rules in README) | Stopped / Notable / Minor | [1], [3] |
| FDA decision calendar (PDUFA dates from 8-Ks, AdComs, approvals, CRLs) with watch/notify | Yes (v0.3.5, `bcf fda-decisions`) | Not stated (unknown) | [1], [3] |
| Trial readout calendar (market-wide primary completions) + watch for slips | Yes (v0.3.6, `bcf readouts`, biocat.ai/calendar) | Completions calendar (paid tier) | [1] |
| Trials at Risk (stopped / overdue / delayed / enrollment shortfall) | Yes (v0.3.6, `bcf readouts at-risk`) | Yes ("Trials at Risk", paid tier) | [1] |
| Digests | RSS, JSON Feed, Markdown, email-ready HTML files (nothing is sent; no hosted email) | Daily email digest + dashboard | [1] |
| Per-record provenance (verified_as_of, verify_hash, source_url) | Yes (v0.3.6) | Not stated (unknown) | [1] |
| FDA advisory committee meetings | Yes (Federal Register notices: committee, date, NDA/BLA, sponsor) | Not stated (unknown) | [1], [3] |
| EMA (EU) regulatory actions | Yes | Not stated (unknown) | [1], [3] |
| openFDA (approvals, submissions, labels) | Yes | Not stated (unknown) | [1] |
| NIH RePORTER grants | Yes | Not stated (unknown) | [1] |
| PubMed / Europe PMC / bioRxiv / medRxiv | Yes (metadata + links; DOI/PMID dedup) | Not stated (unknown) | [1] |
| SEC EDGAR (8-K, PDUFA-date mentions) | Yes | Not stated (unknown) | [1] |
| Ticker → company mapping | Yes (alias table + SEC ticker list, `ticker_confidence` per record) | Unknown | [1] |
| Watch limits | None when self-hosted (subject to each source's rate limits) | Free: 1 sponsor + 1 disease watchlist + 1 saved search; Pro: 10 of each | [1] |
| Schedule | Whenever you run it (cron / Apify schedule) | Daily; updates "typically" within 24 h | [1] |
| Email digest | No (RSS / JSON Feed files instead) | Yes, morning digest | [1] |
| Dashboard / inbox UI | No | Yes (mark changes seen/done) | [1] |
| AI-agent (MCP) access | Yes | Unknown | [1] |
| API / data export | CLI JSON/CSV/Markdown, RSS/JSON Feed, Apify dataset | Unknown | [1] |
| Historical backfill | No: changes only between your own runs | Unknown | [1] |
| Exclude terms / relevance ranking | Yes (`--exclude`, `--rank`) | Saved-search filters exist; details unknown | [1] |
| Setup | Python install (`pip install biocatalystfeed`) | "2 minutes" (their claim) | [1] |
| Support | GitHub issues; contact@biocat.ai | support@datalookout.com (stated for cancellations) | [1] |

**Which to pick.** For a hosted, emailed ClinicalTrials.gov-only digest with a UI and no setup, DataLookout fits.
For several public sources per company or ticker, agent/MCP access, scripting, or self-hosting at no cost,
BioCatalystFeed fits. Both depend on public registries, which can lag: ClinicalTrials.gov sponsors must update key
fields within 30 days of a change (42 CFR 11.64, as cited in [1]).

## Sources
1. DataLookout, "Citeline Alternative for Clinical Trial Monitoring", <https://datalookout.com/citeline-alternative>
   (accessed 2026-10-14).
2. BioCatalystFeed source and README: <https://github.com/biocatalystfeed/biocatalystfeed>.
3. DataLookout, "Automated Clinical Trial Monitoring", <https://datalookout.com/clinical-trial-monitoring> (accessed
   2026-10-21).
