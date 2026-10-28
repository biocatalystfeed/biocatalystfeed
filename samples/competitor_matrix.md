# Competitor matrix: BioCatalystFeed vs DropwatchHQ Bio Catalyst vs DataLookout

Checked 2026-10-28 (PT). BioCatalystFeed (BCF) facts are from this repository at v0.3.6. Competitor facts come only from
their public pages and public, free endpoints (sources at the end). We have not paid for or signed up to either product.
Anything a public page doesn't state is marked **unknown**. Reusable: re-run the checks in "How to refresh" and edit the
cells. Corrections welcome via a GitHub issue.

**DropwatchHQ "bio-catalyst"** is a hosted MCP + REST service (Glama connector `com.dropwatchhq/bio-catalyst`, endpoint
`https://biocatalyst.dropwatchhq.com/mcp`, Streamable HTTP, MCP 2024-11-05). No public source repository was found: the
Glama listing is a *connector* (remote endpoint), not a GitHub-backed server. **DataLookout** is a hosted web app with email
digests for ClinicalTrials.gov changes.

## Feature by feature

| Feature | BioCatalystFeed 0.3.6 | DropwatchHQ Bio Catalyst | DataLookout |
|---|---|---|---|
| Delivery | Open-source Python CLI + local MCP server (stdio), free hosted MCP (9 read-only tools), Apify actor, RSS / JSON Feed / Markdown / HTML digests, public static calendar page (biocat.ai/calendar/, live-refreshed from the hosted worker) | Hosted MCP (3 tools) + REST `/v1/upcoming`, `/v1/company`, `/v1/drug`; web calendar | Hosted web app + email |
| Price | Free, Apache-2.0 | Free tier = next-30-day window and previews; `upcoming_catalysts` $0.02 USDC per call via x402 on Base; paid API keys for full horizon + watchlists (price not stated) | Free (1 sponsor + 1 disease, 1 saved search, 5 tracked trials); Pro $49/mo or $490/yr |
| MCP tools | 32 stdio tools (search / snapshot / changes per source, `changes_feed`, `company_profile`, `fda_decisions`, `readout_calendar`, `trials_at_risk` ...), every parameter described, MCP annotations | `upcoming_catalysts(days, kind, phase, ticker, limit)`, `catalyst_for_company(ticker)`, `catalyst_for_drug(name)`; 2 of 3 tools have undescribed params; no annotations (Glama TDQS A 3.8/5) | None stated (unknown) |
| Upcoming PDUFA dates | **Yes**: `fda_decisions` / `bcf fda-decisions` kind `pdufa`, from company 8-Ks (SEC EDGAR full-text search), labelled `company-disclosed`, with filing link and context | Advertised ("PDUFA/AdComm/trial readouts" in the Glama summary) but **0 PDUFA events** in the free API on 2026-10-28; `kind` enum is only readout / adcom / approval | No |
| FDA AdCom meetings | **Yes**: Federal Register notices; committee, meeting date, NDA/BLA numbers and sponsors parsed from the agenda; postponement / cancellation status | Yes: Federal Register, labelled confirmed (75 on their site; sponsor/drug often null) | No |
| FDA approvals | **Yes**: Drugs@FDA (original + supplements, novel-NME flag, labels); in `fda_decisions` original approvals + efficacy supplements | "recent approvals" kind in the schema; 0 returned on the free tier on 2026-10-28 | No |
| FDA complete response letters | **Yes**: openFDA CRLs with deficiency topics, excerpt, Unapproved → Approved flips | No | No |
| Trial readout calendar (upcoming primary completions, cross-company) | **Yes**: `readout_calendar` / `bcf readouts search` over ClinicalTrials.gov primary completion dates, labelled ESTIMATED / ACTUAL; filters sponsor/ticker, condition, intervention, phase, window, industry-only, ticker-only; watch reports new readouts, slips (delayed / pulled_in), ESTIMATED→ACTUAL; ~930 industry Ph2/3 trials in the next 90 days | **Yes** (core feature; 600 readouts in the free 30-day window) | Completions calendar (paid) |
| Trial change detection | **Yes**: 15+ fields, severity critical / notable / minor, date shift days | No (snapshot calendar only; no diffs stated) | Yes: 13 fields, daily, Stopped / Notable / Minor |
| Watch / notify on FDA decisions | **Yes**: `snapshot_fda_decisions` / `bcf fda-decisions watch`: new events, PDUFA date moved, AdCom postponed/cancelled, CRL → approved; RSS / JSON Feed | "watchlists" on paid keys (details unknown) | No |
| Filters | drug, company/ticker (alias table + SEC ticker list), condition, kinds, date window, upcoming N days, exclude, rank | days, kind, phase, ticker, limit; drug name (separate tool) | Sponsor, disease, saved search (phase, status, start window) |
| Ticker mapping | **Yes, with `ticker_confidence`** (0-1) + `ticker_method` on every record: source ticker 1.0, alias table 0.95, SEC exact name 0.9, SEC prefix 0.6 | Yes, with `tickerConfidence` | No |
| Provenance per record | **Yes**: every record from every tool carries `verified_as_of`, `verify_hash` (sha256 of canonical JSON; `biowatch.provenance.check` re-verifies), `source_url`, plus `provenance {source, field, method}`, `confidence`, `date_precision` | `sourceUrl`, `sourceField`, `verifiedAsOf`, `verifyHash`, confirmation | Unknown |
| Other sources | EMA (EU), NIH RePORTER, PubMed / Europe PMC / bioRxiv / medRxiv, SEC 8-K, opt-in global registry links | None | None |
| Freshness | Live calls to each source on every query (no cache); watches as often as you schedule them | "refreshed daily", `verifiedAsOf` = today | Daily sweep; email next morning |
| Email digest / UI | Digests as RSS, JSON Feed, Markdown and email-ready HTML (`--digest-md/--digest-html`, `changes_feed(format='markdown'|'html')`); public calendar page; **no hosted email sending** (see below) | Web calendar; no email stated | Yes: email digest + dashboard |
| Trials at Risk | **Yes**: `trials_at_risk` / `bcf readouts at-risk`: stopped (suspended/terminated/withdrawn + why_stopped), overdue, stale_overdue, and from snapshot history delayed, enrollment_shortfall, enrollment_cut; risk_score | No | Yes (paid) |
| Historical backfill | No (changes between your own runs) | Unknown | Unknown |
| Self-hosting / scripting | Yes | No | No |

## Parity status (0.3.6)
- **vs DropwatchHQ: at or above parity on every listed feature.** Market-wide readout calendar, per-record
  verified_as_of / verify_hash / source_url, ticker confidence, and a public web calendar shipped in 0.3.6; BCF also
  returns PDUFA dates and approvals (theirs returned none on the free tier), CRLs, Trials at Risk, change watches,
  EMA/NIH/papers, at $0 with no per-call payment.
- **vs DataLookout**: Trials at Risk and rendered digests shipped in 0.3.6. Remaining:
  1. **Hosted email delivery.** BCF writes email-ready HTML/Markdown digests but sends nothing. A free option would need:
     a sender domain with SPF/DKIM (biocat.ai DNS), a free-tier transactional provider (e.g. Cloudflare Email Routing
     only forwards inbound; sending needs a provider such as Resend/Brevo/Mailjet free tiers, all requiring an account
     + API key) or the user's own SMTP via cron (`bcf readouts watch ... --digest-html out.html` + `sendmail`/`msmtp`),
     double opt-in + unsubscribe links (CAN-SPAM/GDPR), and a subscriber store (e.g. Cloudflare D1/KV). Not done: no
     email service was signed up for (project rule).
  2. Dashboard / inbox UI with saved searches (BCF: CLI/MCP + static page).
  3. Landscape reports (indication-level summaries) and CSV export from a UI (BCF has CSV on `trials watch`).
- **Both**: no historical backfill of past values (CT.gov API exposes current values only; history starts with your
  first snapshot). The public calendar page is the 90-day industry Ph2/3 view only; other filters are client-side.

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
