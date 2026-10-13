# Contributing to BioCatalystFeed

Thanks for helping! Issues and pull requests are welcome.

## Dev setup
```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[mcp,dev]'
.venv/bin/python -m pytest -q            # offline tests (no network)
TRIALWATCH_LIVE=1 .venv/bin/python -m pytest -q   # also hits the live public APIs
```

## Ground rules
- **Respect the data sources.** Keep the built-in throttles (ClinicalTrials.gov ≤ ~46 req/min, openFDA 1 req/s,
  NIH RePORTER 1 req/s, NCBI ≤ 3 req/s without key, SEC ≤ 10 req/s with a declared User-Agent). Don't add scrapers for
  sites whose terms forbid it (e.g. proprietary PDUFA calendars).
- **Metadata and links only** for papers and preprints: never store or redistribute abstracts or full text.
- **No personal data or secrets** in code, tests, samples or commits. Configure contacts/keys via environment variables
  (`BIOCATALYSTFEED_CONTACT`, `SEC_USER_AGENT`, `NCBI_EMAIL`).
- **Tests**: every behaviour change needs an offline test using fake clients (see `tests/`). Live tests go behind
  `TRIALWATCH_LIVE`.
- **Style**: small modules per source (`client → normalize → store → core → cli`), standard library + `requests` only
  in the core.
- Keep outputs labelled: anything inferred (e.g. PDUFA candidates) must say UNVERIFIED.

## Licence
By contributing you agree that your contributions are licensed under the Apache License 2.0 (see `LICENSE`), per
section 5 of that licence.
