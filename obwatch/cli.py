"""obwatch CLI: FDA Orange Book patent and exclusivity expiries (public domain U.S. government data)."""
from __future__ import annotations
import argparse, json
from biowatch import digest
from .core import KINDS, SOURCE, OrangeBookClient, loe, protections, run_watch, store


def _q(p):
    p.add_argument("--company", nargs="+", help="applicant name (e.g. 'Novo Nordisk')")
    p.add_argument("--ingredient", nargs="+", help="active ingredient (e.g. semaglutide)")
    p.add_argument("--trade-name", nargs="+", help="brand name (e.g. Ozempic)")
    p.add_argument("--application", help="'NDA 209637', 'ANDA 215328' or '209637'")
    p.add_argument("--kind", nargs="+", choices=KINDS)
    p.add_argument("--since", help="expiry date from YYYY-MM-DD (default today)")
    p.add_argument("--until", help="expiry date up to YYYY-MM-DD")
    p.add_argument("--upcoming-days", type=int, help="only listings expiring within N days")
    p.add_argument("--include-expired", action="store_true")
    p.add_argument("--keyword", help="any word in brand, ingredient, applicant or code")
    p.add_argument("--max", type=int, default=50)
    p.add_argument("--exclude", nargs="+", help="drop rows mentioning these terms")


def _kw(a):
    return dict(company=a.company, ingredient=a.ingredient, trade_name=a.trade_name, application=a.application,
                kind=a.kind, since=a.since, until=a.until, upcoming_days=a.upcoming_days,
                include_expired=a.include_expired, keyword=a.keyword, exclude=a.exclude)


def main(argv=None):
    p = argparse.ArgumentParser("obwatch", description="FDA Orange Book patents and exclusivities. Source: " + SOURCE)
    p.add_argument("--db", default="biowatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="patent/exclusivity listings, soonest expiry first"); _q(s); s.add_argument("--json", action="store_true")
    l = sub.add_parser("loe", help="per application: last listed protection date (loss of exclusivity)"); _q(l); l.add_argument("--json", action="store_true")
    w = sub.add_parser("watch", help="snapshot and diff vs the previous run (new listings, changed expiries, delistings)")
    w.add_argument("--name", required=True); _q(w); digest.add_args(w)
    c = sub.add_parser("changes"); c.add_argument("--name"); c.add_argument("--since")
    a = p.parse_args(argv)
    if a.cmd == "changes":
        for x in store(a.db).changes(watch=a.name, since=a.since): print(json.dumps(x))
        return
    ob = OrangeBookClient()
    if a.cmd == "watch":
        kw = _kw(a); kw.pop("include_expired")
        info = run_watch(ob, store(a.db), a.name, **kw)
        print(f"watch={a.name} run={info['run_id']} listings={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        digest.emit(a, info["changes_detail"], f"BioCatalystFeed Orange Book: {a.name}")
        for x in info["changes_detail"]: print(f"  {x['kind']:24} {x['old'] or ''} -> {x['new'] or ''}  {x['title'][:90]}")
        print(f"Source: {SOURCE}")
        return
    if a.cmd == "loe":
        rows = loe(ob, max_records=a.max, **_kw(a))
        if a.json: print(json.dumps(rows, indent=1)); return
        for r in rows:
            print(f"{r['last_protection'] or '?':10} {r['application']:12} {(r['trade_name'] or '')[:28]:28} {(r['ingredient'] or '')[:30]:30} "
                  f"{(r['applicant'] or '')[:30]:30} {r['last_protection_code']}")
    else:
        rows = protections(ob, max_records=a.max, **_kw(a))
        if a.json: print(json.dumps(rows, indent=1)); return
        for r in rows:
            print(f"{r['expires'] or '?':10} {r['application']:12} {r['kind']:11} {r['code'][:14]:14} {(r['trade_name'] or '')[:26]:26} "
                  f"{(r['ingredient'] or '')[:28]:28} {(r['applicant'] or '')[:28]}")
    print(f"{len(rows)} rows. Listed patents are as submitted by the applicant; FDA does not verify them, and actual generic "
          f"entry can differ. Source: {SOURCE}")


if __name__ == "__main__":
    main()
