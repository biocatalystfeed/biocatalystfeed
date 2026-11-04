# Competitor matrix: BioCatalystFeed vs DropwatchHQ Bio Catalyst vs DataLookout

Checked 2026-11-04 (PT); previous check 2026-10-28. BioCatalystFeed (BCF) facts are from this repository at v0.4.1 and the hosted worker 0.6.0. Competitor facts come only from
their public pages and public, free endpoints (sources at the end). We have not paid for or signed up to either product.
Anything a public page doesn't state is marked **unknown**. Reusable: re-run the checks in "How to refresh" and edit the
cells. Corrections welcome via a GitHub issue.

**DropwatchHQ "bio-catalyst"** is a hosted MCP + REST service (Glama connector `com.dropwatchhq/bio-catalyst`, endpoint
`https://biocatalyst.dropwatchhq.com/mcp`, Streamable HTTP, MCP 2024-11-05). No public source repository was found: the
Glama listing is a *connector* (remote endpoint), not a GitHub-backed server. **DataLookout** is a hosted web app with email
digests for ClinicalTrials.gov changes.

## Feature by feature

| Feature | BioCatalystFeed 0.4.1 (+ hosted 0.6.0) | DropwatchHQ Bio Catalyst | DataLookout |
|---|---|---|---|
| Delivery | Open-source Python CLI + local MCP server (stdio), free hosted MCP (12 read-only tools), Apify actor, RSS / JSON Feed / Markdown / HTML digests, **webhooks (signed JSON, Slack, Discord) on every watch (0.4.1)**, public static calendar page (biocat.ai/calendar/, live-refreshed from the hosted worker) | Hosted MCP (3 tools) + REST `/v1/upcoming`, `/v1/company`, `/v1/drug`; web calendar; **new since 10-28:** per-company and per-drug web pages (`/companies`, `/company/TICKER`, `/drugs`, `/drug/…`), `/adcom`, `/calendar`; webhook alerts on paid plans | Hosted web app + email |
| Price | Free: self-host (BSL 1.1 from 0.4.0; 0.3.6 and earlier Apache-2.0); hosted 200 tool calls/day | **Published 2026-11:** Free $0 (next 30 days, **max 25 rows per call**, now enforced); Self-serve $29/mo (full horizon, 3,000 calls/day, 10 watchlists, webhook alerts, JSON feed + MCP); Pro $99/mo (15,000 calls/day, 500 rows, 50 watchlists, priority refresh, history export); paid in USDC/USDT then email; x402 per-call still offered | Free (1 sponsor + 1 disease, 1 saved search, 5 tracked trials); Pro $49/mo or $490/yr |
| MCP tools | 36 stdio tools (search / snapshot / changes per source, `changes_feed`, `company_profile`, `fda_decisions`, `readout_calendar`, `trials_at_risk`, Orange Book ...), every parameter described, MCP annotations, **server instructions (0.4.1)**; hosted adds `paper_retraction_check`, `condition_landscape`, `condition_momentum` | `upcoming_catalysts(days, kind, phase, ticker, limit)`, `catalyst_for_company(ticker)`, `catalyst_for_drug(name)`; 2 of 3 tools have undescribed params; no annotations (Glama TDQS A 3.8/5) | None stated (unknown) |
| Upcoming PDUFA dates | **Yes**: `fda_decisions` / `bcf fda-decisions` kind `pdufa`, from company 8-Ks (SEC EDGAR full-text search), labelled `company-disclosed`, with filing link and context | Advertised ("PDUFA/AdComm/trial readouts" in the Glama summary) but **0 PDUFA events** in the free API on 2026-10-28 and 2026-11-04; their llms.txt now lists only readouts + AdComs | No |
| FDA AdCom meetings | **Yes**: Federal Register notices; committee, meeting date, NDA/BLA numbers and sponsors parsed from the agenda; postponement / cancellation status | Yes: Federal Register, labelled confirmed (75 on their site; free API returned 1 on 2026-11-04) | No |
| FDA approvals | **Yes**: Drugs@FDA (original + supplements, novel-NME flag, labels); in `fda_decisions` original approvals + efficacy supplements | "recent approvals" kind in the schema; 0 returned on the free tier on 2026-10-28 | No |
| FDA complete response letters | **Yes**: openFDA CRLs with deficiency topics, excerpt, Unapproved → Approved flips | No | No |
| Trial readout calendar (upcoming primary completions, cross-company) | **Yes**: `readout_calendar` / `bcf readouts search` over ClinicalTrials.gov primary completion dates, labelled ESTIMATED / ACTUAL; filters sponsor/ticker, condition, intervention, phase, window, industry-only, ticker-only; watch reports new readouts, slips (delayed / pulled_in), ESTIMATED→ACTUAL; ~900 industry Ph2/3 trials in the next 90 days (calendar.json 894 on 2026-11-04) | **Yes** (core feature; site claims 601 upcoming catalysts, 257 mapped to tickers; free tier capped at 25 rows) | Completions calendar (paid) |
| Trial change detection | **Yes**: 15+ fields, severity critical / notable / minor, date shift days | No (snapshot calendar only; no diffs stated) | Yes: 13 fields, daily, Stopped / Notable / Minor |
| Watch / notify on FDA decisions | **Yes**: `snapshot_fda_decisions` / `bcf fda-decisions watch`: new events, PDUFA date moved, AdCom postponed/cancelled, CRL → approved; RSS / JSON Feed | Watchlists (10 / 50 tickers or drugs) + webhook alerts on new catalysts, paid plans only | No |
| Filters | drug, company/ticker (alias table + SEC ticker list), condition, kinds, date window, upcoming N days, exclude, rank | days, kind, phase, ticker, limit; drug name (separate tool) | Sponsor, disease, saved search (phase, status, start window) |
| Ticker mapping | **Yes, with `ticker_confidence`** (0-1) + `ticker_method` on every record: source ticker 1.0, alias table 0.95, SEC exact name 0.9, SEC prefix 0.6 | Yes, with `tickerConfidence` | No |
| Provenance per record | **Yes**: every record from every tool carries `verified_as_of`, `verify_hash` (sha256 of canonical JSON; `biowatch.provenance.check` re-verifies), `source_url`, plus `provenance {source, field, method}`, `confidence`, `date_precision` | `sourceUrl`, `sourceField`, `verifiedAsOf`, `verifyHash`, confirmation; new fields `sourceApi`, `verificationMethod`, `sourceAnchored`, `dateGranularity`, `lastUpdate`, `sponsorClass` | Unknown |
| Other sources | EMA (EU), NIH RePORTER, PubMed / Europe PMC / bioRxiv / medRxiv, SEC 8-K, FDA Orange Book (patents, exclusivities, LOE dates; 0.4.1), opt-in global registry links; hosted retraction check | None | None |
| Freshness | Live calls to each source on every query (no cache); watches as often as you schedule them | "refreshed daily", `verifiedAsOf` = today | Daily sweep; email next morning |
| Email digest / UI | Digests as RSS, JSON Feed, Markdown and email-ready HTML (`--digest-md/--digest-html`, `changes_feed(format='markdown'|'html')`); public calendar page; **no hosted email sending** (see below) | Web calendar; no email stated | Yes: email digest + dashboard |
| Trials at Risk | **Yes**: `trials_at_risk` / `bcf readouts at-risk`: stopped (suspended/terminated/withdrawn + why_stopped), overdue, stale_overdue, and from snapshot history delayed, enrollment_shortfall, enrollment_cut; risk_score | No | Yes (paid) |
| Push alerts (webhook / chat) | **Yes (0.4.1)**: `--webhook URL` on every watch; JSON with HMAC-SHA256 signature, Slack or Discord format; free | Webhook alerts on paid plans ($29+/mo) | Email only |
| Landscape / disease-area reports | **Yes (hosted 0.6.0)**: `condition_landscape` (sponsors by phase with tickers, phase distribution, new-entrant sponsors, new trials, upcoming readouts, recently stopped) and `condition_momentum` (compare up to 8 disease areas: new trials, active Ph3, stops, documented momentum score); MCP only, no web page | No | Yes: landscape reports (sponsors by phase, phase chart, recent protocol changes, new entrants) and "Pipeline Pulse" ranking 88 disease areas by momentum; web UI |
| Per-company / per-drug web pages | `company_profile` (MCP/CLI) and the calendar page; **no per-company web pages** | **Yes** (new, SEO pages) | Sponsor pipeline pages |
| Historical backfill / history export | No backfill (changes between your own runs); full local snapshot history in SQLite, CSV on `trials watch`, JSON changes | History export on Pro ($99/mo) | Unknown |
| Self-hosting / scripting | Yes | No | No |

## Parity status (0.4.1 + hosted 0.6.0, 2026-11-04)
- **vs DropwatchHQ**: at or above parity on data and alerts. Their new paid webhook alerts are matched for free by
  0.4.1 webhooks; BCF still returns PDUFA dates and approvals (theirs: none on the free tier), CRLs, Trials at Risk,
  landscapes and change watches at $0. **Gap:** per-company / per-drug public web pages (SEO). BCF has the data
  (`company_profile`, calendar.json) but no generated pages yet.
- **vs DataLookout**: landscape reports and Pipeline-Pulse-style momentum now exist on the hosted MCP (0.6.0). Remaining:
  1. **Hosted email delivery.** BCF writes email-ready digests and now pushes webhooks (Slack/Discord/any URL), but
     sends no email. A free hosted option needs a sending provider account + API key, SPF/DKIM on biocat.ai, double
     opt-in/unsubscribe and a subscriber store. Not done: no provider signup (project rule). Self-hosters can use
     `--digest-html` + their own SMTP.
  2. Dashboard / inbox UI with saved searches, and landscape *web pages* (BCF's landscape is MCP/JSON only).
  3. Momentum across all disease areas at once (DataLookout ranks 88; `condition_momentum` compares up to 8 per call).
- **Both**: no historical backfill of past values (CT.gov API exposes current values only; history starts with your
  first snapshot).

## How to refresh
- DropwatchHQ: `curl https://biocatalyst.dropwatchhq.com/v1/upcoming?days=90` (free), `/v1/company?ticker=PFE`,
  `/v1/drug?name=tirzepatide`, `/.well-known/x402`, `/llms.txt`; MCP `tools/list` on `/mcp`; Glama connector page.
  Do not pay x402 calls (project rule: $0 spend).
- DataLookout: homepage pricing table, /citeline-alternative, /clinical-trial-landscape-analysis.
- DropwatchHQ pricing: /pricing; SEO pages /companies, /drugs.

## Sources
1. Glama, "bio-catalyst - MCP Connector", <https://glama.ai/mcp/connectors/com.dropwatchhq/bio-catalyst> (accessed 2026-11-04).
2. DropwatchHQ, "API & MCP", <https://biocatalyst.dropwatchhq.com/developers>; `/llms.txt`; `/.well-known/x402`; free `/v1/upcoming`, `/v1/company`, `/v1/drug` responses and MCP `tools/list`; /pricing, /companies, /drugs (accessed 2026-11-04).
3. DataLookout homepage <https://datalookout.com/> and <https://datalookout.com/citeline-alternative>, <https://datalookout.com/clinical-trial-landscape-analysis> (accessed 2026-11-04).
4. BioCatalystFeed README and CHANGELOG, <https://github.com/biocatalystfeed/biocatalystfeed>.
