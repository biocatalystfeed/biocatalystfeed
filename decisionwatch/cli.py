"""`bcf fda-decisions`: upcoming PDUFA dates (company 8-Ks), AdComs, approvals and CRLs with provenance; watch + notify."""
from __future__ import annotations
import argparse, json
from biowatch import digest
from .core import KINDS, decisions, run_watch, store


def _clients():
    from fdawatch.client import OpenFDAClient
    from adcomwatch.core import FRClient
    from secwatch.core import SECClient
    return OpenFDAClient(), FRClient(), SECClient()


def _q(p):
    p.add_argument("--drug", help="drug name or code (e.g. 'tirzepatide', 'VK2735')")
    p.add_argument("--company", help="company name or ticker (alias-resolved; unknown tickers looked up in SEC's ticker list)")
    p.add_argument("--condition", help="condition / disease text (e.g. 'obesity')")
    p.add_argument("--kinds", nargs="+", choices=KINDS, help="event kinds (default all)")
    p.add_argument("--since", help="event date from YYYY-MM-DD"); p.add_argument("--until", help="event date to YYYY-MM-DD")
    p.add_argument("--upcoming", type=int, metavar="DAYS", help="only pdufa/adcom events from today to today+DAYS")
    p.add_argument("--max", type=int, default=50)
    p.add_argument("--max-docs", type=int, default=20, help="max SEC 8-K documents to parse for PDUFA dates")


def _kw(a):
    return dict(kinds=a.kinds, drug=a.drug, company=a.company, condition=a.condition, since=a.since, until=a.until,
                upcoming_days=a.upcoming, max_docs=a.max_docs)


def main(argv=None):
    p = argparse.ArgumentParser("bcf fda-decisions", description="FDA decision calendar: PDUFA dates (company-disclosed, SEC 8-K), "
                                "AdCom meetings (Federal Register), approvals (Drugs@FDA), CRLs (openFDA). Not investment advice.")
    p.add_argument("--db", default="biowatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="merged events: upcoming soonest first, then past newest first"); _q(s); s.add_argument("--json", action="store_true")
    w = sub.add_parser("watch", help="snapshot and diff vs the previous run (new events, date/status/confidence changes)")
    w.add_argument("--name", required=True); _q(w); digest.add_args(w)
    c = sub.add_parser("changes", help="stored changes"); c.add_argument("--name"); c.add_argument("--since")
    a = p.parse_args(argv)
    if a.cmd == "changes":
        for x in store(a.db).changes(watch=a.name, since=a.since): print(json.dumps(x))
        return
    if a.cmd == "watch":
        info = run_watch(*_clients(), store(a.db), a.name, **_kw(a))
        print(f"watch={a.name} run={info['run_id']} events={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        digest.write(info["changes_detail"], f"BioCatalystFeed FDA decisions: {a.name}", a.rss, a.json_feed, getattr(a, "digest_md", None), getattr(a, "digest_html", None))
        for x in info["changes_detail"]: print(f"  {x['kind']:26} {x['old'] or ''} -> {x['new'] or ''}  {x['title'][:80]} {x['url']}")
        for e in info["errors"]: print(f"  source error ({e['kind']}): {e['error']}")
        return
    errors: list = []
    rows = decisions(*_clients(), max_records=a.max, errors=errors, **_kw(a))
    if a.json: print(json.dumps({"events": rows, "errors": errors}, indent=1)); return
    for r in rows:
        print(f"{r['date'] or '?':10} {r['kind']:8} {r['confidence']:17} {(r['ticker'] or '')[:6]:6} {(r['title'] or '')[:90]:90} {r['url']}")
    for e in errors: print(f"source error ({e['kind']}): {e['error']}")
    print(f"{len(rows)} events. pdufa = company-disclosed in SEC 8-Ks (UNVERIFIED regex extraction; FDA does not publish "
          "PDUFA dates); adcom = Federal Register notice; approval/crl = FDA records. Not investment advice.")


if __name__ == "__main__":
    main()
