# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report privately via GitHub: **Security → Report a vulnerability** on
<https://github.com/biocatalystfeed/biocatalystfeed/security/advisories/new>.

Include affected version (`bcf --version`), steps to reproduce and impact. We aim to acknowledge
within 3 business days and to ship a fix or mitigation for confirmed issues within 30 days, and we
credit reporters in the release notes unless you prefer otherwise.

## Supported versions

Only the latest release on PyPI receives fixes.

## Scope

In scope: the `biocatalystfeed` Python package (CLI, MCP server, local SQLite stores), the Apify
actor in `actor/`, and the website/demo at biocatalystfeed.com (separate repo).
Out of scope: the upstream public data APIs (ClinicalTrials.gov, openFDA, NIH RePORTER, NCBI,
Europe PMC, bioRxiv, SEC EDGAR) and the accuracy of their data.

## Design notes

- No API keys are required; optional keys (openFDA, NCBI) are read from environment variables and never logged.
- All SQLite access uses parameterised queries. Output files are only written to paths you pass explicitly.
- MCP tool inputs are validated (NCT IDs, enumerated values) and result sizes are capped.
