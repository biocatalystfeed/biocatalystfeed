# BioCatalystFeed Hosted Services: Terms of Service

_Effective: 2026-10-21_

These terms cover the hosted BioCatalystFeed services operated by the BioCatalystFeed project ("BioCatalystFeed",
"we", "us"): the public hosted MCP endpoint (Cloudflare Workers, `/mcp`) and BioCatalystFeed listings on third-party
marketplaces such as Apify (together, "the Service"). The software is licensed separately (Business Source License 1.1 for
0.4.0 and later; Apache-2.0 for 0.3.6 and earlier); these terms do not restrict your rights under those licences. If you run the software yourself, only the
licence and the data sources' own terms apply.

By using the Service you agree to these terms. If you do not agree, do not use the Service.

## 1. What the Service is
The Service retrieves public data and returns it to you in a structured form. The hosted MCP endpoint offers a
read-only subset of tools that query ClinicalTrials.gov, openFDA, PubMed, and the Federal Register. The full software
and marketplace versions may also use the European Medicines Agency (EMA), NIH RePORTER, Europe PMC, bioRxiv/medRxiv,
and SEC EDGAR. We don't create the underlying data, and we are not affiliated with or endorsed by any of these sources.

## 2. Not advice
**Nothing in the Service is investment, legal, or medical advice.** Data may be incomplete, delayed, or wrong.
PDUFA dates are unverified candidates extracted from SEC filings. Check primary sources before you rely on anything.
You alone are responsible for your decisions.

## 3. No account; eligibility
The hosted MCP endpoint needs no account. Marketplace use requires an account with that marketplace under its terms.
You must be at least 18, or the age of majority where you live, to use the Service.

## 4. Fair use and rate limits
The hosted endpoint is free and rate-limited per IP address (currently 200 tool calls per UTC day and 30 requests per minute;
requests over the limit get HTTP 429). We may change limits at any time. Don't: break the law; try to get around rate limits (for example
by rotating IP addresses); overload, scan, or attack the Service; resell or redistribute raw Service output as a
competing data feed; or use the Service to break any data source's terms or infringe third-party rights in records
(for example preprint licences). We may block traffic that does any of these.

## 5. Data-source terms and attribution
Data comes from third parties under their own terms, which also apply to you, including:
- **ClinicalTrials.gov** (U.S. National Library of Medicine): no implied NLM endorsement.
- **openFDA**: "Data provided by the U.S. Food and Drug Administration (https://open.fda.gov)." Not validated for
  clinical or production use.
- **PubMed / NCBI**: citation metadata; abstracts may be under publisher copyright.
- **Federal Register** (Office of the Federal Register, NARA): U.S. government works.
- **European Medicines Agency**: "Source: European Medicines Agency (EMA), https://www.ema.europa.eu." Reproduced under
  EMA's copyright and limited reproduction notice; reuse requires acknowledging EMA as the source. EMA does not endorse
  BioCatalystFeed.
- Others used by the full software (NIH RePORTER, Europe PMC, bioRxiv/medRxiv, SEC EDGAR fair-access policy).
See `NOTICE` for the full list.

## 6. Paid marketplace use
The hosted MCP endpoint is free. If you use BioCatalystFeed through a paid marketplace listing, the price, billing,
renewal, and refunds are set by that listing and the marketplace's terms. We'll give at least 30 days' notice of price
changes on our own listings.

## 7. Availability and changes
The Service is provided without an uptime commitment. Upstream sources change or go offline; we may change, limit,
suspend, or discontinue the Service or any feature at any time.

## 8. Disclaimer of warranties
THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE", WITHOUT WARRANTIES OF ANY KIND, INCLUDING MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE, ACCURACY, AND NON-INFRINGEMENT.

## 9. Limitation of liability
TO THE EXTENT THE LAW ALLOWS, WE ARE NOT LIABLE FOR INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES,
OR FOR TRADING LOSSES OR LOST PROFITS. OUR TOTAL LIABILITY IS LIMITED TO THE GREATER OF THE AMOUNT YOU PAID US IN THE
12 MONTHS BEFORE THE CLAIM OR US$50.

## 10. Indemnity
You will indemnify us against claims arising from your misuse of the Service or your breach of these terms.

## 11. Termination
You may stop using the Service at any time. We may block or suspend access that breaches these terms.

## 12. Governing law
These terms are governed by the laws of Florida, United States, without regard to conflict-of-law rules; disputes go to
the courts of that state, except where the law where you live gives you the right to bring a claim locally.

## 13. Changes to these terms
We'll post updates in this file with a new effective date. Continued use after an update means you accept it.

## Contact
contact@biocat.ai
