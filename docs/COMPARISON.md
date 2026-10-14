# BioCatalystFeed vs DataLookout: coverage comparison

Checked 2026-10-14 (PT). DataLookout facts come only from its public page
<https://datalookout.com/citeline-alternative> (the only DataLookout page cited here). BioCatalystFeed facts come from
this repository (v0.2.1). We have **not** used DataLookout's product; anything its public page doesn't state is
marked **unknown**. Corrections welcome via a GitHub issue.

The two tools overlap only on ClinicalTrials.gov change monitoring. DataLookout is a hosted, emailed product.
BioCatalystFeed is open-source software you run yourself (CLI, MCP server, Apify actor).

| | BioCatalystFeed | DataLookout | DataLookout source |
|---|---|---|---|
| Delivery model | Self-hosted Python package (PyPI), MCP server, Apify actor | Hosted web app + email | [1] |
| Price | Free, Apache-2.0 (Apify runs use your own Apify plan/credits) | Free tier; Pro $49/month, monthly or yearly, cancel anytime | [1] |
| ClinicalTrials.gov | Yes (API v2): search, sponsor pipeline, diffs between your runs | Yes: daily snapshot + diff | [1] |
| Trial fields diffed | Status, phase, enrollment, key dates, sponsor, title, why-stopped, results posting | 13 fields "including overall status, enrollment, primary endpoints, interventions, results posting, site counts, and completion dates"; full list unknown | [1] |
| Change severity labels | No (raw field-level changes) | Stopped / Notable / Minor | [1] |
| openFDA (approvals, submissions, labels) | Yes | Not stated (unknown) | [1] |
| NIH RePORTER grants | Yes | Not stated (unknown) | [1] |
| PubMed / Europe PMC / bioRxiv / medRxiv | Yes (metadata + links; DOI/PMID dedup) | Not stated (unknown) | [1] |
| SEC EDGAR (8-K, PDUFA-date mentions) | Yes | Not stated (unknown) | [1] |
| Ticker → company mapping | Yes (alias table) | Unknown | [1] |
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
