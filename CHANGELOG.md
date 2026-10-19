# Changelog

## Unreleased
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
