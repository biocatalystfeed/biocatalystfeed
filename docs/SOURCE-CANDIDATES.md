# Source candidates (vetted list)

Maintained by the weekly source scout. A source ships only if it passes **every** gate below and fits the product.

**Gates (all must pass):** (G1) official government/regulator or established peer-reviewed/indexed origin; (G2) stable
public API or bulk download; (G3) terms allow redistribution or derived alerts; (G4) no paywall or scraping around
access controls; (G5) no sanctions or export-control concern.
**Fit (1-5):** how much a new catalyst signal it adds beyond what BioCatalystFeed already covers.
**Score** = fit if all gates pass, otherwise 0 (blocked), with the failing gate named.

Already shipped: ClinicalTrials.gov, openFDA, NIH RePORTER, PubMed, Europe PMC, bioRxiv/medRxiv, SEC EDGAR,
**EMA (shipped 2026-10-19)**, **Federal Register FDA advisory committee notices (shipped 2026-10-21)**.

| Source | G1 | G2 | G3 | G4 | G5 | Fit | Score | Status / why |
|---|---|---|---|---|---|---|---|---|
| **EMA medicines data** (EU regulator) | ✅ | ✅ daily JSON export (~2.7k medicines) | ✅ reuse incl. commercial with EMA acknowledged in each copy (EMA legal notice) | ✅ | ✅ | 5 | **5** | **Shipped 2026-10-19** as `bcf ema`. CHMP opinions, EC decisions, refusals, withdrawals; first international regulator. Attribution carried on every record, CLI output, feeds and NOTICE. |
| **Federal Register API** (FDA notices) | ✅ U.S. Office of the Federal Register | ✅ documented JSON API, no key (checked 2026-10-19) | ✅ U.S. government works, public domain | ✅ | ✅ | 4 | **4** | **Shipped 2026-10-21** as `bcf adcom`. Meeting / amendment / postponement / cancellation notices only (nominations, renewals, RFIs dropped); tobacco excluded by default; agenda parsed for NDA/BLA numbers and sponsors. |
| **ISRCTN registry** (UK, WHO primary registry) | ✅ | 🟡 XML API exists but its docs are labelled "draft" | ✅ study records usable under CC-BY per ISRCTN FAQ | ✅ | ✅ | 3 | **3** | Candidate. Adds UK/EU trials not on ClinicalTrials.gov. Wait for or test API stability before shipping; publisher is BioMed Central (Springer Nature). |
| **OpenAlex** (scholarly index) | ✅ established open index | ✅ free API | ✅ data CC0 | ✅ | ✅ | 2 | **2** | Low priority: mostly overlaps PubMed/Europe PMC; could help with citation counts / affiliations later. |
| **Health Canada Drug Product Database** | ✅ regulator | ❓ API did not respond during the 2026-10-19 check | ❓ Open Government Licence – Canada expected; confirm | ✅ | ✅ | 2 | **–** | Re-check. Marketed-product data, weaker catalyst signal than EMA. |
| **WHO ICTRP** (global trial registry hub) | ✅ | ❓ access is via a WHO-arranged web service / crawling service, not an open API | ❓ terms not yet confirmed | ✅ | ✅ | 4 | **0 (G2/G3 unconfirmed)** | Would cover ChiCTR, jRCT, CTRI, EU CTR etc. in one feed. Worth an inquiry to WHO about terms; would need a maintainer decision if it requires an agreement or fees. |
| **EU CTIS** (EU trials portal) | ✅ EMA | ❌ no documented public API (only the website's internal endpoints) | ✅ EMA reuse terms | ⚠️ would mean using undocumented endpoints | ✅ | 4 | **0 (G2)** | Revisit if EMA publishes an API or bulk export. |
| **Japan jRCT** | ✅ MHLW | ❌ no documented public API or bulk export found | ❓ | ⚠️ scraping | ✅ | 3 | **0 (G2)** | Japanese trials reach WHO ICTRP; better path is ICTRP. |
| **China ChiCTR** | ✅ | ❌ no public API | ❓ terms unclear | ⚠️ scraping | 🟡 China data-export rules make bulk harvesting a gray area | 3 | **0 (G2/G5)** | Not pursued directly; ICTRP is the cleaner route if ever. |
| **China NMPA approvals** | ✅ regulator | ❌ no API; website only, with anti-bot measures | ❓ | ⚠️ scraping | 🟡 | 3 | **0 (G2/G4)** | Not pursued. |
| **CNKI** (Chinese journals) | ✅ | ❌ | ❌ subscription | ❌ paywall | 🟡 | – | **0 (G3/G4)** | Excluded. Chinese-journal papers indexed in PubMed / Europe PMC are already covered by `bcf papers`. |
| medRxiv / bioRxiv | ✅ | ✅ | ✅ metadata + links | ✅ | ✅ | – | shipped | Already in `bcf papers`. |

## Log
- 2026-10-21: shipped Federal Register AdCom notices (re-checked: documented JSON API, no key; U.S. government works).
  Next candidate: ISRCTN once its API docs leave "draft".
- 2026-10-19: first scout run. Shipped EMA. Queued Federal Register (FDA AdCom notices) for the next run. No source
  needed a paid or legal call this week; WHO ICTRP may need one later if its terms require an agreement.
