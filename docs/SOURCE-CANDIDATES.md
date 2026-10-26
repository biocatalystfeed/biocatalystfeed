# Source candidates (vetted list)

Maintained by the weekly source scout. A source ships only if it passes **every** gate below and fits the product.

**Gates (all must pass):** (G1) official government/regulator or established peer-reviewed/indexed origin; (G2) stable
public API or bulk download; (G3) terms allow redistribution or derived alerts; (G4) no paywall or scraping around
access controls; (G5) no sanctions or export-control concern.
**Fit (1-5):** how much a new catalyst signal it adds beyond what BioCatalystFeed already covers.
**Score** = fit if all gates pass, otherwise 0 (blocked), with the failing gate named.

Already shipped: ClinicalTrials.gov, openFDA, NIH RePORTER, PubMed, Europe PMC, bioRxiv/medRxiv, SEC EDGAR,
**EMA (shipped 2026-10-19)**, **Federal Register FDA advisory committee notices (shipped 2026-10-21)**, **openFDA complete response letters (shipped 2026-10-26)**.

| Source | G1 | G2 | G3 | G4 | G5 | Fit | Score | Status / why |
|---|---|---|---|---|---|---|---|---|
| **EMA medicines data** (EU regulator) | ✅ | ✅ daily JSON export (~2.7k medicines) | ✅ reuse incl. commercial with EMA acknowledged in each copy (EMA legal notice) | ✅ | ✅ | 5 | **5** | **Shipped 2026-10-19** as `bcf ema`. CHMP opinions, EC decisions, refusals, withdrawals; first international regulator. Attribution carried on every record, CLI output, feeds and NOTICE. |
| **Federal Register API** (FDA notices) | ✅ U.S. Office of the Federal Register | ✅ documented JSON API, no key (checked 2026-10-19) | ✅ U.S. government works, public domain | ✅ | ✅ | 4 | **4** | **Shipped 2026-10-21** as `bcf adcom`. Meeting / amendment / postponement / cancellation notices only (nominations, renewals, RFIs dropped); tobacco excluded by default; agenda parsed for NDA/BLA numbers and sponsors. |
| **openFDA complete response letters** (FDA) | ✅ FDA | ✅ documented openFDA endpoint `transparency/crl.json`, no key (458 letters, newest 2026-08-07, checked 2026-10-26) | ✅ openFDA CC0 / public domain | ✅ | ✅ | 4 | **4** | **Shipped 2026-10-26** as `bcf crl`. New signal: FDA's reasons for not approving an NDA/BLA (facility, CMC, clinical, safety ...), plus Unapproved → Approved flips. Updated "infrequently" by FDA, so letters lag. Personal fields (rep, signatory, address) not copied. Not on the hosted endpoint yet. |
| **FDA Orange Book data files** | ✅ FDA | ✅ monthly ZIP (`fda.gov/media/76860/download`, responded 2026-10-26) | ✅ U.S. government work, public domain | ✅ | ✅ | 3 | **3** | Next candidate. Patent and exclusivity expiry dates per NDA (loss-of-exclusivity catalysts). Needs a monthly-diff design; fda.gov can be slow/bot-sensitive, so cache the ZIP and use a polite UA. |
| **FDA Purple Book** (biologics) | ✅ FDA | ✅ monthly downloadable files on purplebooksearch.fda.gov (page responded 2026-10-26) | ✅ public domain | ✅ | ✅ | 2 | **2** | Biologic licensure, reference-product exclusivity, biosimilar/interchangeable status. Pair with Orange Book later. |
| **openFDA drug shortages** | ✅ FDA | ✅ `drug/shortages.json` (1,611 records, updated 2026-10-23) | ✅ CC0 | ✅ | ✅ | 2 | **2** | Low catalyst value for small-cap biotech; easy to add to `bcf fda` later. |
| **ISRCTN registry** (UK, WHO primary registry) | ✅ | 🟡 public XML API, no key, responded 2026-10-26, but docs are still "Draft" v0.6 dated 18/08/2023 and the FAQ still says "draft and may be incomplete" | ✅ records CC BY 4.0, metadata CC0 (ISRCTN FAQ, re-checked 2026-10-26) | ✅ | ✅ | 3 | **3** | Candidate (unchanged). The API has been unchanged for 3 years and CRAN `ctrdata` uses it, but the docs are still marked draft. Option: ask the ISRCTN editorial team whether the API is supported for production reuse. Most industry trials here are also on ClinicalTrials.gov, so fit stays 3. |
| **OpenAlex** (scholarly index) | ✅ established open index | ✅ free API | ✅ data CC0 | ✅ | ✅ | 2 | **2** | Low priority: mostly overlaps PubMed/Europe PMC; could help with citation counts / affiliations later. |
| **Health Canada Drug Product Database** | ✅ regulator | ✅ JSON API answered via the fetch service on 2026-10-26 (no key; timed out from the build box, so check reachability before shipping); bulk `allfiles.zip` on open.canada.ca | ✅ Open Government Licence – Canada (commercial reuse with source attribution) | ✅ | ✅ | 2 | **2** | All gates pass now; fit stays low (marketed products, not approval events). Health Canada's Notice of Compliance (NOC) data would be the stronger signal; check it next run. |
| **WHO ICTRP** (global trial registry hub) | ✅ | ❌ no open API. The crawling service is "currently not available", partner-only, and charged to business entities | ❌ download terms §4d: no use "for marketing, promotional or commercial purposes"; crawling partners may not charge third parties | ✅ | ✅ | 4 | **0 (G2/G3)** | Blocked for any paid tier. **Owner decision** (2026-10-26): no ICTRP data until licensed. A licence would mean a written agreement and a fee (amount on request). Global add-on stays link-out only. |
| **EU CTIS** (EU trials portal) | ✅ EMA | ❌ still no documented public API or bulk export (2026-10-26). `ctis-public-api` is the portal's undocumented backend (community tools use it; capped at 10k results); only its 15-item RSS feed is linked by EMA | ✅ EMA reuse terms | ⚠️ undocumented endpoints | ✅ | 4 | **0 (G2)** | Unchanged. Revisit if EMA documents the API or publishes bulk data. |
| **Japan jRCT** | ✅ MHLW | ❌ no documented public API or bulk export found | ❓ | ⚠️ scraping | ✅ | 3 | **0 (G2)** | Japanese trials reach WHO ICTRP; better path is ICTRP. |
| **China ChiCTR** | ✅ | ❌ no public API | ❓ terms unclear | ⚠️ scraping | 🟡 China data-export rules make bulk harvesting a gray area | 3 | **0 (G2/G5)** | Not pursued directly; ICTRP is the cleaner route if ever. |
| **China NMPA approvals** | ✅ regulator | ❌ no API; website only, with anti-bot measures | ❓ | ⚠️ scraping | 🟡 | 3 | **0 (G2/G4)** | Not pursued. |
| **ANZCTR** (Australia/NZ registry) | ✅ | ❌ no public API; site returned HTTP 403 to a scripted request (2026-10-26) | ❓ | ⚠️ bot block | ✅ | 3 | **0 (G2/G4)** | Not pursued; already a link-out in the Global add-on. |
| **CNKI** (Chinese journals) | ✅ | ❌ | ❌ subscription | ❌ paywall | 🟡 | – | **0 (G3/G4)** | Excluded. Chinese-journal papers indexed in PubMed / Europe PMC are already covered by `bcf papers`. |
| medRxiv / bioRxiv | ✅ | ✅ | ✅ metadata + links | ✅ | ✅ | – | shipped | Already in `bcf papers`. |

## Log
- 2026-10-26: shipped openFDA complete response letters as `bcf crl` (score 4: documented openFDA endpoint, CC0, new
  "why FDA said no" signal). Re-checks: ISRCTN still 3 (API live, docs still "Draft" v0.6 from 2023); Health Canada DPD
  scored at 2 (API answers, OGL-Canada confirmed); WHO ICTRP now 0 for G2/G3 (no open API, no commercial use, paid
  partner crawling, licence needed per the 2026-10-26 owner decision); EU CTIS still 0 (G2). New: Orange Book 3 (next
  candidate), Purple Book 2, openFDA drug shortages 2, ANZCTR 0 (G2/G4). ChiCTR/ICTRP data is still not ingested; the Global
  add-on stays link-out only.
- 2026-10-21: shipped Federal Register AdCom notices (re-checked: documented JSON API, no key; U.S. government works).
  Next candidate: ISRCTN once its API docs leave "draft".
- 2026-10-19: first scout run. Shipped EMA. Queued Federal Register (FDA AdCom notices) for the next run. No source
  needed a paid or legal call this week; WHO ICTRP may need one later if its terms require an agreement.
