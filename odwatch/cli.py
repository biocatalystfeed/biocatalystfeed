"""odwatch CLI: FDA orphan drug designations and approvals (OOPD database; public domain U.S. government data)."""
from __future__ import annotations
import argparse, json
from biowatch import digest
from .core import CAVEAT, DATE_BY, SOURCE, STATUSES, OOPDClient, designations, exclusivities, run_watch, store


def _q(p, watch=False):
    p.add_argument("--company", nargs="+", help="sponsor name (e.g. 'Cardiff Oncology')")
    p.add_argument("--product", nargs="+", help="generic or trade name (e.g. onvansertib)")
    p.add_argument("--condition", nargs="+", help="words in the designation or approved indication (e.g. 'small cell lung')")
    p.add_argument("--status", nargs="+", choices=STATUSES, type=str.lower,
                   help="designated (active, not yet approved), approved, withdrawn (withdrawn or revoked)")
    p.add_argument("--country", nargs="+", help="sponsor country (e.g. China)")
    p.add_argument("--since", help="date from YYYY-MM-DD"); p.add_argument("--until", help="date up to YYYY-MM-DD")
    p.add_argument("--days", type=int, help="only the last N days")
    p.add_argument("--date-by", choices=DATE_BY, default="designated",
                   help="which date --since/--until/--days filter and sort on (default: designation date)")
    p.add_argument("--keyword", help="any word in product, designation, indication or sponsor")
    p.add_argument("--exclude", nargs="+", help="drop rows mentioning these terms")
    if not watch: p.add_argument("--max", type=int, default=50); p.add_argument("--json", action="store_true")


def _kw(a):
    return dict(company=a.company, product=a.product, condition=a.condition, status=a.status, country=a.country,
                since=a.since, until=a.until, recent_days=a.days, date_by=a.date_by, keyword=a.keyword, exclude=a.exclude)


def main(argv=None):
    p = argparse.ArgumentParser("odwatch", description="FDA orphan drug designations and approvals. Source: " + SOURCE)
    p.add_argument("--db", default="biowatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="orphan designations (one row per designation), newest first"); _q(s)
    x = sub.add_parser("exclusivity", help="orphan-drug exclusivity end dates (7 years from approval), soonest first")
    x.add_argument("--company", nargs="+"); x.add_argument("--product", nargs="+")
    x.add_argument("--since", help="end date from YYYY-MM-DD (default today)"); x.add_argument("--until", help="end date up to YYYY-MM-DD")
    x.add_argument("--upcoming-days", type=int, help="only exclusivities ending within N days")
    x.add_argument("--include-expired", action="store_true"); x.add_argument("--exclude", nargs="+")
    x.add_argument("--max", type=int, default=50); x.add_argument("--json", action="store_true")
    w = sub.add_parser("watch", help="snapshot and diff vs the previous run (new designations, approvals, withdrawals, sponsor changes)")
    w.add_argument("--name", required=True); _q(w, watch=True); digest.add_args(w)
    c = sub.add_parser("changes"); c.add_argument("--name"); c.add_argument("--since")
    a = p.parse_args(argv)
    if a.cmd == "changes":
        for r in store(a.db).changes(watch=a.name, since=a.since): print(json.dumps(r))
        return
    cl = OOPDClient()
    if a.cmd == "watch":
        info = run_watch(cl, store(a.db), a.name, **_kw(a))
        print(f"watch={a.name} run={info['run_id']} designations={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        digest.emit(a, info["changes_detail"], f"BioCatalystFeed FDA orphan designations: {a.name}")
        for r in info["changes_detail"]: print(f"  {r['kind']:24} {r['old'] or ''} -> {r['new'] or ''}  {r['title'][:90]}")
        print(f"Source: {SOURCE}")
        return
    if a.cmd == "exclusivity":
        rows = exclusivities(cl, company=a.company, product=a.product, since=a.since, until=a.until, upcoming_days=a.upcoming_days,
                             include_expired=a.include_expired, exclude=a.exclude, max_records=a.max)
        if a.json: print(json.dumps(rows, indent=1)); return
        for r in rows:
            print(f"{r['exclusivity_end']}  approved {r['approval_date'] or '?':10} {(r['trade_name'] or r['generic_name'] or '')[:26]:26} "
                  f"{(r['sponsor'] or '')[:30]:30} {(r['protected_indication'] or '')[:60]}")
        print(f"{len(rows)} rows. {CAVEAT} Source: {SOURCE}")
        return
    rows = designations(cl, max_records=a.max, **_kw(a))
    if a.json: print(json.dumps(rows, indent=1)); return
    for r in rows:
        print(f"{r['designated_date'] or '?':10} {r['state']:10} {(r['generic_name'] or '')[:30]:30} {(r['sponsor'] or '')[:28]:28} "
              f"{(r['designation'] or '')[:50]:50} {('approved ' + r['latest_approval_date']) if r['latest_approval_date'] else ''}")
    print(f"{len(rows)} rows. {CAVEAT} Source: {SOURCE}")


if __name__ == "__main__":
    main()
