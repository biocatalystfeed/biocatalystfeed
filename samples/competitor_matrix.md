# Competitor matrix: BioCatalystFeed vs DropwatchHQ Bio Catalyst vs DataLookout

Checked 2026-10-28 (PT). BioCatalystFeed (BCF) facts are from this repository at v0.3.5. Competitor facts come only from
their public pages and public, free endpoints (sources at the end). We have not paid for or signed up to either product.
Anything a public page doesn't state is marked **unknown**. Reusable: re-run the checks in "How to refresh" and edit the
cells. Corrections welcome via a GitHub issue.

**DropwatchHQ "bio-catalyst"** is a hosted MCP + REST service (Glama connector `com.dropwatchhq/bio-catalyst`, endpoint
`https://biocatalyst.dropwatchhq.com/mcp`, Streamable HTTP, MCP 2024-11-05). No public source repository was found: the
Glama listing is a *connector* (remote endpoint), not a GitHub-backed server. **DataLookout** is a hosted web app with email
digests for ClinicalTrials.gov changes.

## Feature by feature

| Feature | BioCatalystFeed 0.3.5 | DropwatchHQ Bio Catalyst | DataLookout |
|---|---|---|---|
| Delivery | Open-source Python CLI + local MCP server (stdio), free hosted MCP (7 read-only tools), Apify actor, RSS / JSON Feed | Hosted MCP (3 tools) + REST `/v1/upcoming`, `/v1/company`, `/v1/drug`; web calendar | Hosted web app + email digest |
| Price | Free, Apache-2.0 | Free tier = next-30-day window and previews; `upcoming_catalysts` $0.02 USDC per call via x402 on Base; paid API keys for full horizon + watchlists (price not stated) | Free (1 sponsor + 1 disease, 1 saved search, 5 tracked trials); Pro $49/mo or $490/yr |
| MCP tools | 28 stdio tools (search / snapshot / changes per source, `changes_feed`, `company_profile`, `fda_decisions` ...), every parameter described, MCP annotations | `upcoming_catalysts(days, kind, phase, ticker, limit)`, `catalyst_for_company(ticker)`, `catalyst_for_drug(name)`; 2 of 3 tools have undescribed params; no annotations (Glama TDQS A 3.8/5) | None stated (unknown) |
| Upcoming PDUFA dates | **Yes**: `fda_decisions` / `bcf fda-decisions` kind `pdufa`, from company 8-Ks (SEC EDGAR full-text search), labelled `company-disclosed`, with filing link and context | Advertised ("PDUFA/AdComm/trial readouts" in the Glama summary) but **0 PDUFA events** in the free API on 2026-10-28; `kind` enum is only readout / adcom / approval | No |
| FDA AdCom meetings | **Yes**: Federal Register notices; committee, meeting date, NDA/BLA numbers and sponsors parsed from the agenda; postponement / cancellation status | Yes: Federal Register, labelled confirmed (75 on their site; sponsor/drug often null) | No |
| FDA approvals | **Yes**: Drugs@FDA (original + supplements, novel-NME flag, labels); in `fda_decisions` original approvals + efficacy supplements | "recent approvals" kind in the schema; 0 returned on the free tier on 2026-10-28 | No |
| FDA complete response letters | **Yes**: openFDA CRLs with deficiency topics, excerpt, Unapproved → Approved flips | No | No |
| Trial readout calendar (upcoming primary completions, cross-company) | Partial: per company (`company_profile.next_primary_completions`) and via `search_trials`; **no market-wide "readouts in next N days" view** | **Yes**: ~600 upcoming readouts, labelled estimated, sourceField given | Pro: "Completions calendar" |
| Trial change detection | **Yes**: 15+ fields, severity critical / notable / minor, date shift days | No (snapshot calendar only; no diffs stated) | Yes: 13 fields, daily, Stopped / Notable / Minor |
| Watch / notify on FDA decisions | **Yes**: `snapshot_fda_decisions` / `bcf fda-decisions watch`: new events, PDUFA date moved, AdCom postponed/cancelled, CRL → approved; RSS / JSON Feed | "watchlists" on paid keys (details unknown) | No |
| Filters | drug, company/ticker (alias table + SEC ticker list), condition, kinds, date window, upcoming N days, exclude, rank | days, kind, phase, ticker, limit; drug name (separate tool) | Sponsor, disease, saved search (phase, status, start window) |
| Ticker mapping | Alias table + SEC company_tickers (pdufa events carry the SEC ticker) | Yes, with `tickerConfidence` (258 of 602 events mapped) | No |
| Provenance per record | `url` (official record) + `provenance {source, field, method}` + `confidence` + `date_precision` | `source`, `sourceUrl`, `sourceField`, `sourceApi`, `verifiedAsOf`, `verifyHash`, `confirmation` | Links to the CT.gov record |
| Other sources | EMA (EU), NIH RePORTER, PubMed / Europe PMC / bioRxiv / medRxiv, SEC 8-K, opt-in global registry links | None | None |
| Freshness | Live calls to each source on every query (no cache); watches as often as you schedule them | "refreshed daily", `verifiedAsOf` = today | Daily sweep; email next morning |
| Email digest / UI | No (RSS / JSON Feed files; any reader or automation) | Web calendar; no email stated | Yes: email digest + dashboard |
| Historical backfill | No (changes between your own runs) | Unknown | Unknown |
| Self-hosting / scripting | Yes | No | No |

## Parity status (BCF vs DropwatchHQ)
- At or above parity: AdComs, approvals, PDUFA (BCF actually returns PDUFA dates; theirs returns none on the free tier),
  CRLs, ticker/drug lookup, watch + notify, provenance + confidence, tool-schema quality, price ($0 vs x402 per call).
- **Remaining gaps vs DropwatchHQ**
  1. Market-wide upcoming trial-readout calendar (`upcoming_readouts(days, phase, ticker)` over ClinicalTrials.gov
     primary-completion dates, labelled estimated). BCF can do this per company or per search, not as one calendar.
  2. Per-record `verifyHash` / `verifiedAsOf` stamp (BCF has `provenance.retrieved` on live calls only).
  3. `tickerConfidence` score on sponsor → ticker mapping, and ticker mapping for CT.gov sponsors outside the alias table.
  4. A public web calendar page (BCF site shows source cards, not a live calendar).
- **Remaining gaps vs DataLookout**: hosted daily email digest, dashboard inbox, "Trials at Risk" list, landscape reports.

## How to refresh
- DropwatchHQ: `curl https://biocatalyst.dropwatchhq.com/v1/upcoming?days=90` (free), `/v1/company?ticker=PFE`,
  `/v1/drug?name=tirzepatide`, `/.well-known/x402`, `/llms.txt`; MCP `tools/list` on `/mcp`; Glama connector page.
  Do not pay x402 calls (project rule: $0 spend).
- DataLookout: homepage pricing table and /citeline-alternative.

## Sources
1. Glama, "bio-catalyst - MCP Connector", <https://glama.ai/mcp/connectors/com.dropwatchhq/bio-catalyst> (accessed 2026-10-28).
2. DropwatchHQ, "API & MCP", <https://biocatalyst.dropwatchhq.com/developers>; `/llms.txt`; `/.well-known/x402`; free `/v1/upcoming`, `/v1/company`, `/v1/drug` responses and MCP `tools/list` (accessed 2026-10-28).
3. DataLookout homepage <https://datalookout.com/> and <https://datalookout.com/citeline-alternative> (accessed 2026-10-28).
4. BioCatalystFeed README and CHANGELOG, <https://github.com/biocatalystfeed/biocatalystfeed>.
