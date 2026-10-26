# Changelog

## Unreleased
- New source: FDA complete response letters (CRLs) from openFDA's transparency endpoint (`bcf crl search|watch|changes` / `crlwatch`; MCP tools `fda_complete_response_letters`, `snapshot_crl`, `crl_changes_since`; `changes_feed` accepts `crl`). Filters: company, application number, letter-date window, application status (Approved since / Unapproved), keyword (drug or any word in the letter), deficiency topic. Each record has a best-effort product name, deficiency topics from the letter's section headings, an excerpt of the first deficiency and the FDA PDF link. Watches report new letters and Unapproved → Approved flips. Personal fields in the source (company representative, signatory, address) are not copied. openFDA data is public domain / CC0. Not yet on the hosted endpoint.

## 0.3.2 — 2026-10-26
- Opt-in Global coverage (off by default; default outputs unchanged): links to records in non-FDA/EMA registries (e.g. ChiCTR, other WHO-listed national registries) plus paper jurisdiction flags. `--global` / `--global-sources` on `bcf trials search` and `bcf papers search`; `include_global` / `global_sources` on MCP `search_trials` and `search_papers` (stdio and hosted).
  - Trials: labelled link-outs (`registry_class: "non-FDA/EMA registry"`, `registry`, `jurisdiction`, `source_url`, `also_registered_as`) for ChiCTR, CTRI, jRCT/JPRN, CRIS, ANZCTR, ReBEC, PACTR, IRCT, TCTR and ISRCTN IDs found in ClinicalTrials.gov secondary IDs. Link only: no foreign registry data is fetched, scraped or stored. WHO ICTRP data, ChiCTR pages and the NMPA/CDE platform are not ingested.
  - Papers: `jurisdiction_flag` ("non-FDA/EMA oversight" / "unknown") and `jurisdiction` from Europe PMC author-affiliation countries; never guessed.
  - Text output prefixes labels and prints the standard disclaimer once; JSON adds `global_disclaimer`; RSS/JSON Feed items with `registry_class` get the label prefix and disclaimer.
  - One-line stderr tip on searches without `--global` (TTY only; off with `--quiet`, `--json` or `BCF_NO_TIPS=1`); `bcf --global --help` detail text; docs/GLOBAL.md.

## 0.3.1 — 2026-10-21
- PubMed `--since`/`--until` now filter on the publication date that is displayed (esearch uses `pdat`, plus an exact local filter on the shown date); previously the filter used Entrez date (`edat`), so older-looking papers could appear. Test added.
- openFDA: per-request timeouts (3 s connect / 6 s read), at most 2 retries with short capped backoff, and a 15 s total budget, so an openFDA outage fails in about 15 s instead of minutes. Tests added.
- `bcf trials changes` prints a readable summary by default; `--json` gives the previous JSON-lines output.
- README: venv-first Quickstart (macOS PEP 668), `uvx`/`pipx` options, note that `--db` goes after the tool name, and a Contributing/Testing section (`pip install -e '.[dev]'`, `pytest`, `TRIALWATCH_LIVE=1`).

## 0.3.0 — 2026-10-21
- New source: FDA advisory committee meetings from the Federal Register API (`bcf adcom search|upcoming|watch|changes` / `adcomwatch`; MCP tools `fda_adcom_meetings`, `snapshot_adcom`, `adcom_changes_since`; `changes_feed` accepts `adcom`). Parses committee, meeting date, kind (meeting / amendment / postponement / cancellation), and NDA/BLA numbers and sponsors from each notice's agenda. Federal Register documents are U.S. government works (public domain).
- ClinicalTrials.gov diffs now also track primary endpoints, arm count, interventions, site count and results-first-posted date. Snapshots from older versions start tracking the new fields on their next run (no false "changes" on upgrade).
- Every trial change has a `severity` (critical / notable / minor) and date changes have `shift_days`; `--min-severity` on `bcf trials watch` / `changes`, `min_severity` on MCP `trial_changes_since`; markdown reports sort critical first and RSS/JSON Feed titles show the severity.
- New source: European Medicines Agency (EMA) medicines data (`bcf ema` / `emawatch`, MCP tools `ema_medicines`, `snapshot_ema`, `ema_changes_since`; `changes_feed` accepts `ema`). Tracks CHMP opinions, EC decisions, refusals, withdrawals and suspensions from EMA's official daily JSON export; every record carries EMA source attribution as EMA's reuse terms require.
- Primary website is now https://biocat.ai; project contact and SEC User-Agent default contact are now `contact@biocat.ai`.

## 0.2.2 — 2026-10-14
- SEC User-Agent default contact is now `contact@biocatalystfeed.com` (was a `.invalid` placeholder).
- Optional `OPENFDA_API_KEY` and `NCBI_API_KEY` environment variables are now read and documented in the README.
- Launch hardening: jittered backoff, `Retry-After` support and network-error retries; NCT ID validation; MCP input clamps; friendly CLI errors.
- Added SECURITY.md, CODE_OF_CONDUCT.md, issue/PR templates, gitleaks config.

## 0.2.1
- Search filters (exclude wildcards/comma lists), better relevance ranking, Europe PMC keywords.
- MCP Registry `server.json`, `glama.json`, COMPARISON.md, TERMS/PRIVACY.

## 0.2.0
- Initial open-source release.
