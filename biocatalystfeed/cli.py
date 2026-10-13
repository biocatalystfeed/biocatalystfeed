"""`biocatalystfeed` / `bcf` umbrella CLI: dispatches to the per-source tools (old commands still work as aliases)."""
from __future__ import annotations
import importlib, sys
from . import __version__, DISCLAIMER

TOOLS = {"trials": "trialwatch.cli", "fda": "fdawatch.cli", "grants": "grantwatch.cli", "papers": "paperwatch.cli",
         "sec": "secwatch.cli", "mcp": "trialwatch.mcp_server"}
ALIASES = {"trialwatch": "trials", "fdawatch": "fda", "grantwatch": "grants", "paperwatch": "papers", "secwatch": "sec",
           "profile": "fda"}

USAGE = f"""BioCatalystFeed {__version__}
usage: biocatalystfeed <tool> [args...]     (short: bcf)

tools:
  trials   ClinicalTrials.gov search / watch / pipeline      (= trialwatch)
  fda      openFDA approvals, labels, company profiles       (= fdawatch)
  grants   NIH RePORTER grants                               (= grantwatch)
  papers   PubMed + Europe PMC + bioRxiv/medRxiv             (= paperwatch)
  sec      SEC EDGAR 8-K PDUFA mentions (UNVERIFIED)         (= secwatch)
  profile  merged company profile                            (= fdawatch profile)
  mcp      run the MCP server over stdio                     (= trialwatch-mcp)

{DISCLAIMER}"""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
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
    return mod.main(rest)


if __name__ == "__main__":
    sys.exit(main())
