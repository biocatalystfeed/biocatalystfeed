# Competitor matrix: BioCatalystFeed vs DropwatchHQ Bio Catalyst vs DataLookout

Checked 2026-11-25 (ET); previous check 2026-11-18. BioCatalystFeed (BCF) facts are from this repository at v0.4.4, the hosted worker 0.6.1
and the live biocat.ai calendar pages (site PRs #23 / #24 merged 2026-11-18; data refresh PR #44 merged 2026-11-25). Competitor facts come only from
their public pages and public, free endpoints (sources at the end). We have not paid for or signed up to either product.
Anything a public page doesn't state is marked **unknown**. Reusable: re-run the checks in "How to refresh" and edit the
cells. Corrections welcome via a GitHub issue.

**DropwatchHQ "bio-catalyst"** is a hosted MCP + REST service (Glama connector `com.dropwatchhq/bio-catalyst`, endpoint
`https://biocatalyst.dropwatchhq.com/mcp`, Streamable HTTP, MCP 2024-11-05). No public source repository was found: the
Glama listing is a *connector* (remote endpoint), not a GitHub-backed server. **DataLookout** is a hosted web app with email
digests for ClinicalTrials.gov changes.

## Feature by feature

| Feature | BioCatalystFeed 0.4.4 (+ hosted 0.6.1) | DropwatchHQ Bio Catalyst | DataLookout |
|---|---|---|---|
| Delivery | Open-source Python CLI + local MCP server (stdio), free hosted MCP (12 read-only tools), Apify actor, RSS / JSON Feed / Markdown / HTML digests, **webhooks (signed JSON, Slack, Discord) on every watch (0.4.1)**, public static calendar site (biocat.ai/calendar/, live-refreshed from the hosted worker) with per-company pages + per-company .ics feeds and per-month pages (0.4.2); **iCalendar (.ics) export** of readouts and FDA decisions (0.4.2); **live since 2026-11-18 (PRs #23 / #24)**, refreshed 2026-11-25 (PR #44): FDA events on month + company pages, month archive back to 2023-09 (53 months), 341 company pages, `/calendar/fda/`, 1,497 drug pages, 91 disease-area pages | Hosted MCP (3 tools) + REST `/v1/upcoming`, `/v1/company`, `/v1/drug`; web calendar; **new since 10-28:** per-company and per-drug web pages (`/companies`, `/company/TICKER`, `/drugs`, `/drug/…`), `/adcom`, `/calendar`; **new since 11-04:** `/calendar/readouts` and 35 monthly `/date/YYYY-MM` pages (back to 2023-09); sitemap 127 company + 598 drug pages; **2026-11-18:** sitemap 771 URLs = 606 drug + 122 company + 35 month (`/date/2023-09` ...) + `/adcom`, lastmod 2026-11-18; **2026-11-25:** sitemap 765 URLs = 605 drug + 117 company + 35 month (`/date/2023-09` ... `/date/2027-03`) + `/adcom`, `/developers` (REST + MCP docs page), lastmod 2026-11-25; still no .ics or RSS feed (`/calendar.ics`, `/feed.json`, `/rss.xml` 404 on 2026-11-25); webhook alerts on paid plans | Hosted web app + email |
| Price | Free: self-host (BSL 1.1 from 0.4.0; 0.3.6 and earlier Apache-2.0); hosted 200 tool calls/day | **Published 2026-11:** Free $0 (next 30 days, **max 25 rows per call**, now enforced); Self-serve $29/mo (full horizon, 3,000 calls/day, 10 watchlists, webhook alerts, JSON feed + MCP); Pro $99/mo (15,000 calls/day, 500 rows, 50 watchlists, priority refresh, history export); paid in USDC/USDT then email; x402 per-call still offered | Free (1 sponsor + 1 disease, 1 saved search, 5 tracked trials); Pro $49/mo or $490/yr |
| MCP tools | 51 stdio tools (search / snapshot / changes per source, `list_watches` (0.4.2), FDA Purple Book tools (0.4.3), FDA orphan designation tools and **`get_paper` / `get_grant` ID lookups (0.4.4)**, `changes_feed`, `company_profile`, `fda_decisions`, `readout_calendar`, `trials_at_risk`, Orange Book ...), every parameter described, MCP annotations, **server instructions (0.4.1)**; hosted adds `paper_retraction_check`, `condition_landscape`, `condition_momentum` | `upcoming_catalysts(days, kind, phase, ticker, limit)`, `catalyst_for_company(ticker)`, `catalyst_for_drug(name)`; 2 of 3 tools have undescribed params; no annotations (Glama TDQS A 3.8/5, scored 2026-07-28, unchanged 2026-11-25; connector last tested 2026-11-25; `kind` enum now readout / adcom / approval, no pdufa). BCF on Glama: TDQS A 3.8/5 (scored 2026-11-05, 36 tools, **not rescored as of 2026-11-25**; Disambiguation 3, Naming 3, Tool count 3, Completeness 4; asked for list-watches (shipped 0.4.2) and get-by-ID for papers / grants / Orange Book (papers + grants shipped 0.4.4; Orange Book has `application=`)); maintenance "Maintained", responsiveness "Outdated data" | None stated (unknown) |
| Upcoming PDUFA dates | **Yes**: `fda_decisions` / `bcf fda-decisions` kind `pdufa`, from company 8-Ks (SEC EDGAR full-text search), labelled `company-disclosed`, with filing link and context (40 dated PDUFA events on 2026-11-18, 25 upcoming in the site build); 0.4.3 stops common words (`disease`, `release`) showing as the drug | Advertised ("PDUFA/AdComm/trial readouts" in the Glama summary) but **0 PDUFA events** in the free API on 2026-10-28, 11-04, 11-11, 11-18 and 11-25 (`kind=pdufa`, 180 days: count 0); llms.txt and the MCP `kind` enum list only readouts, AdComs and approvals | No |
| FDA AdCom meetings | **Yes**: Federal Register notices; committee, meeting date, NDA/BLA numbers and sponsors parsed from the agenda; postponement / cancellation status | Yes: Federal Register, labelled confirmed (75 on their site; free API returned 1 on 2026-11-04, 11-11 and 11-18, 0 of 25 rows on 11-25) | No |
| FDA approvals | **Yes**: Drugs@FDA (original + supplements, novel-NME flag, labels); in `fda_decisions` original approvals + efficacy supplements. **0.4.3 fix:** market-wide queries had silently dropped ~30% of a 90-day window (500-application cap; 157 of 227 found on 2026-11-18) | "approval" kind in the MCP schema; 0 returned on the free tier on 2026-10-28 (not re-tested) | No |
| FDA complete response letters | **Yes**: openFDA CRLs with deficiency topics, excerpt, Unapproved → Approved flips | No | No |
| Trial readout calendar (upcoming primary completions, cross-company) | **Yes**: `readout_calendar` / `bcf readouts search` over ClinicalTrials.gov primary completion dates, labelled ESTIMATED / ACTUAL; filters sponsor/ticker, condition, intervention, phase, window, industry-only, ticker-only; watch reports new readouts, slips (delayed / pulled_in), ESTIMATED→ACTUAL; ~900 industry Ph2/3 trials in the next 90 days (915 on 2026-11-18, 902 on 11-25) | **Yes** (core feature; site claims 601 upcoming catalysts (600 readouts + 75 AdComs), 266 mapped to tickers on 2026-11-25 (262 on 11-18); free tier capped at 25 rows: free `/v1/upcoming?days=90` returned 25 readouts on 2026-11-25) | Completions calendar (paid) |
| Trial change detection | **Yes**: 15+ fields, severity critical / notable / minor, date shift days | No (snapshot calendar only; no diffs stated) | Yes: 13 fields, daily, Stopped / Notable / Minor |
| Watch / notify on FDA decisions | **Yes**: `snapshot_fda_decisions` / `bcf fda-decisions watch`: new events, PDUFA date moved, AdCom postponed/cancelled, CRL → approved; RSS / JSON Feed | Watchlists (10 / 50 tickers or drugs) + webhook alerts on new catalysts, paid plans only | No |
| Filters | drug, company/ticker (alias table + SEC ticker list), condition, kinds, date window, upcoming N days, exclude, rank | days, kind, phase, ticker, limit; drug name (separate tool) | Sponsor, disease, saved search (phase, status, start window) |
| Ticker mapping | **Yes, with `ticker_confidence`** (0-1) + `ticker_method` on every record: source ticker 1.0, alias table 0.95, SEC exact name 0.9, SEC prefix 0.6 | Yes, with `tickerConfidence` | No |
| Provenance per record | **Yes**: every record from every tool carries `verified_as_of`, `verify_hash` (sha256 of canonical JSON; `biowatch.provenance.check` re-verifies), `source_url`, plus `provenance {source, field, method}`, `confidence`, `date_precision` | `sourceUrl`, `sourceField`, `verifiedAsOf`, `verifyHash`, confirmation; new fields `sourceApi`, `verificationMethod`, `sourceAnchored`, `dateGranularity`, `lastUpdate`, `sponsorClass` | Unknown |
| Other sources | EMA (EU), NIH RePORTER, PubMed / Europe PMC / bioRxiv / medRxiv, SEC 8-K, FDA Orange Book (patents, exclusivities, LOE dates; 0.4.1), FDA Purple Book (licensed biologics, biosimilar / interchangeable landscape; 0.4.3), FDA orphan drug designations + orphan exclusivity (0.4.4), Health Canada NOCs, opt-in global registry links; hosted retraction check | None | None |
| Freshness | Live calls to each source on every query (no cache); watches as often as you schedule them | "refreshed daily", `verifiedAsOf` = today | Daily sweep; email next morning |
| Email digest / UI | Digests as RSS, JSON Feed, Markdown and email-ready HTML (`--digest-md/--digest-html`, `changes_feed(format='markdown'|'html')`); public calendar page; **no hosted email sending** (see below) | Web calendar; no email stated | Yes: email digest + dashboard (homepage shows the latest sweep: 1,071 changes on 580 trials on 2026-11-25; 953 on 524 on 11-18) |
| Trials at Risk | **Yes**: `trials_at_risk` / `bcf readouts at-risk`: stopped (suspended/terminated/withdrawn + why_stopped), overdue, stale_overdue, and from snapshot history delayed, enrollment_shortfall, enrollment_cut; risk_score | No | Yes (paid) |
| Push alerts (webhook / chat) | **Yes (0.4.1)**: `--webhook URL` on every watch; JSON with HMAC-SHA256 signature, Slack or Discord format; free | Webhook alerts on paid plans ($29+/mo) | Email only |
| Landscape / disease-area reports | **Yes (hosted 0.6.0; 0.6.1 fixes intermittent CPU-limit 503s on large conditions)**: `condition_landscape` (sponsors by phase with tickers, phase distribution, new-entrant sponsors, new trials, upcoming readouts, recently stopped) and `condition_momentum` (compare up to 8 disease areas per call: new trials, active Ph3, stops, documented momentum score). **Live web pages (since 2026-11-18, refreshed weekly):** 91 disease-area landscape pages + a momentum ranking of all 91 areas | No | Yes: landscape reports (sponsors by phase, phase chart, recent protocol changes, new entrants) and "Pipeline Pulse" ranking 88 disease areas by momentum; web UI |
| Per-company / per-drug web pages | **Live (2026-11-25 data):** 341 per-ticker pages with FDA events + last 12 months, 53 month pages 2023-09 to 2028-01 with readouts + FDA events, 1,497 per-drug pages (stricter junk-name filter: comparators, background / standard-of-care, chemotherapy classes and formulation labels no longer get pages), 91 disease-area pages, `/calendar/fda/`. Each ticker page has a subscribable `.ics`; sitemap + schema.org Event JSON-LD | **Yes**: 117 company + 605 drug + 35 month pages (sitemap 2026-11-25; was 122 / 606 / 35 on 11-18) | **135** `-clinical-trials` landing pages on 2026-11-25 (99 disease-area, 25 sponsor, 11 modality, e.g. `/obesity-clinical-trials`, `/eli-lilly-clinical-trials`, `/glp-1-receptor-agonist-clinical-trials`; unchanged since 11-18; sitemap 160 URLs), 4 'alternative to' pages, 11 blog posts |
| Historical backfill / history export | No backfill (changes between your own runs); full local snapshot history in SQLite, CSV on `trials watch`, JSON changes | History export on Pro ($99/mo) | Unknown |
| Calendar feeds (.ics) | **Yes (0.4.2)**: `--ics` on `bcf readouts` / `bcf fda-decisions`; hosted `biocat.ai/calendar/calendar.ics` + one per ticker | No (unknown on paid plans) | No |
| CSV export | Yes (`bcf trials watch` CSV; JSON everywhere) | History export on Pro | CSV export on Pro ($49/mo) |
| Self-hosting / scripting | Yes | No | No |

## Parity status (0.4.4 + hosted 0.6.1, 2026-11-25)
- **vs DropwatchHQ**: at or above parity on data, alerts and static pages (PDUFA dates, approvals, CRLs, Trials at Risk,
  landscapes, change watches, webhooks and .ics feeds, all free). No product changes seen on their side this week (same 3
  tools, pricing, 25-row free cap, still 0 PDUFA events; sitemap 771 -> 765 URLs, a `/developers` API page). Since PRs
  #23 / #24 went live, BCF has more pages of every kind they have: 341 company pages (vs 117), 53 months (vs 35), 1,497
  drug pages (vs 605), plus FDA-decision and disease-area pages they don't have. Glama TDQS still tied at A 3.8/5 (ours
  not rescored since 2026-11-05; 0.4.4 adds the get-by-ID tools Glama asked for).
- **vs DataLookout**: landscape and momentum are live as web pages (91 disease-area pages with sponsor-by-phase
  landscapes, new entrants and recent stops, plus a ranking of all 91 areas, vs their 88-area Pipeline Pulse and 99
  disease pages). No changes on their side this week (160-URL sitemap unchanged). Still open:
  1. **Hosted email delivery** (needs a sending-provider signup; not allowed). Self-hosters: `--digest-html` + SMTP.
  2. Dashboard / inbox UI with saved searches (BCF: MCP, CLI, webhooks, static pages; no logged-in UI).
  3. Sponsor-name and modality landing pages (they have 25 sponsor + 11 modality pages; BCF has per-ticker pages,
     which cover listed sponsors only, and no modality pages). A new page type, so it needs owner review.
  4. 'Alternative to' comparison pages (they have 4); BCF has `docs/COMPARISON.md` only (new page type; owner review).
- **Both**: no historical backfill of past *values* (CT.gov API exposes current values only; history starts with your
  first snapshot). BCF's month archive shows past primary completion dates as currently recorded, not past versions.

## How to refresh
- DropwatchHQ: `curl https://biocatalyst.dropwatchhq.com/v1/upcoming?days=90` (free), `/v1/company?ticker=PFE`,
  `/v1/drug?name=tirzepatide`, `/.well-known/x402`, `/llms.txt`; MCP `tools/list` on `/mcp`; Glama connector page.
  Do not pay x402 calls (project rule: $0 spend).
- DataLookout: homepage pricing table, /citeline-alternative, /clinical-trial-landscape-analysis.
- DropwatchHQ pricing: /pricing; SEO pages /companies, /drugs, /date/YYYY-MM; `/sitemap.xml` for page counts.
- DataLookout: `/sitemap.xml` for landing-page counts.
- Glama: connector page and `glama.ai/mcp/servers/biocatalystfeed/biocatalystfeed` for TDQS scores.
- DropwatchHQ PDUFA probe: `/v1/upcoming?days=180&kind=pdufa` (count). Feed probes: `/calendar.ics`, `/feed.json`, `/rss.xml`.

## Sources
1. Glama, "bio-catalyst - MCP Connector", <https://glama.ai/mcp/connectors/com.dropwatchhq/bio-catalyst> (accessed 2026-11-25).
2. DropwatchHQ <https://biocatalyst.dropwatchhq.com/> homepage, `/llms.txt`, `/pricing`, `/sitemap.xml`, free `/v1/upcoming?days=90` and `?days=180&kind=pdufa`, MCP `tools/list` on `/mcp`; `/calendar.ics`, `/feed.json`, `/rss.xml` (404) (accessed 2026-11-25). Official MCP Registry search "dropwatch" (com.dropwatchhq/bio-catalyst 1.0.0).
3. DataLookout homepage <https://datalookout.com/> (pricing, sweep counts, Pipeline Pulse) and <https://datalookout.com/sitemap.xml> (160 URLs) (accessed 2026-11-25).
4. Glama, BioCatalystFeed server page <https://glama.ai/mcp/servers/biocatalystfeed/biocatalystfeed> (accessed 2026-11-25).
5. BioCatalystFeed README and CHANGELOG, <https://github.com/biocatalystfeed/biocatalystfeed>; site PRs <https://github.com/biocatalystfeed/biocatalystfeed.github.io/pull/23> and <https://github.com/biocatalystfeed/biocatalystfeed.github.io/pull/24>, data refresh <https://github.com/biocatalystfeed/biocatalystfeed.github.io/pull/44>.
