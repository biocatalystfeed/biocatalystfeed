"""`biocatalystfeed` / `bcf` umbrella CLI: dispatches to the per-source tools (old commands still work as aliases)."""
from __future__ import annotations
import importlib, os, sys
from . import __version__, DISCLAIMER

TOOLS = {"trials": "trialwatch.cli", "fda": "fdawatch.cli", "grants": "grantwatch.cli", "papers": "paperwatch.cli",
         "sec": "secwatch.cli", "ema": "emawatch.cli", "adcom": "adcomwatch.cli", "crl": "crlwatch.cli", "fda-decisions": "decisionwatch.cli", "mcp": "trialwatch.mcp_server"}
ALIASES = {"trialwatch": "trials", "fdawatch": "fda", "grantwatch": "grants", "paperwatch": "papers", "secwatch": "sec", "emawatch": "ema", "adcomwatch": "adcom", "crlwatch": "crl", "decisions": "fda-decisions", "pdufa": "fda-decisions",
           "profile": "fda"}

USAGE = f"""BioCatalystFeed {__version__}
usage: biocatalystfeed <tool> [args...]     (short: bcf)

tools:
  trials   ClinicalTrials.gov search / watch / pipeline      (= trialwatch)
  fda      openFDA approvals, labels, company profiles       (= fdawatch)
  grants   NIH RePORTER grants                               (= grantwatch)
  papers   PubMed + Europe PMC + bioRxiv/medRxiv             (= paperwatch)
  sec      SEC EDGAR 8-K PDUFA mentions (UNVERIFIED)         (= secwatch)
  ema      EMA (EU) opinions, authorisations, withdrawals     (= emawatch)
  adcom    FDA advisory committee meetings (Federal Register) (= adcomwatch)
  crl      FDA complete response letters (openFDA)           (= crlwatch)
  fda-decisions  FDA decision calendar + watch: PDUFA dates (8-K), AdComs, approvals, CRLs
  profile  merged company profile                            (= fdawatch profile)
  mcp      run the MCP server over stdio                     (= trialwatch-mcp)

options:
  --global on `trials search` / `papers search`: opt-in, off by default; adds labelled
           non-FDA/EMA registry link-outs and paper jurisdiction flags. Details: bcf --global --help

{DISCLAIMER}"""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--global":
        from biowatch.globalcov import HELP
        print(HELP); return 0
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE); return 0
    if argv[0] in ("-V", "--version"):
        print(__version__); return 0
    tool = ALIASES.get(argv[0], argv[0])
    if tool not in TOOLS:
        print(f"unknown tool {argv[0]!r}\n\n{USAGE}", file=sys.stderr); return 2
    rest = argv[1:]
    if argv[0] == "profile": rest = ["profile"] + rest
    mod = importlib.import_module(TOOLS[tool])
    if tool == "mcp": return mod.main()
    try:
        return mod.main(rest)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # friendly one-line errors; BCF_DEBUG=1 for the traceback
        if os.environ.get("BCF_DEBUG"): raise
        print(f"bcf {argv[0]}: error: {_explain(e)}", file=sys.stderr)
        return 1


def _explain(e: Exception) -> str:
    import requests
    if isinstance(e, requests.HTTPError) and e.response is not None:
        r = e.response
        host = r.url.split("/")[2] if "://" in r.url else r.url
        if r.status_code == 429:
            return f"{host} is rate-limiting requests (HTTP 429). Wait a minute and retry."
        if r.status_code >= 500:
            return f"{host} is having problems (HTTP {r.status_code}). Retry later."
        return f"{host} rejected the request (HTTP {r.status_code}). Check your arguments."
    if isinstance(e, (requests.ConnectionError, requests.Timeout)):
        return f"network problem reaching the data source ({type(e).__name__}). Check your connection and retry."
    return str(e) or type(e).__name__


if __name__ == "__main__":
    sys.exit(main())
