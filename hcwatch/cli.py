"""hcwatch CLI: Health Canada Notices of Compliance (Open Government Licence - Canada)."""
from __future__ import annotations
import argparse, json
from biowatch import digest
from .core import SOURCE, SUB_CODES, NOCClient, notices, run_watch, store


def _q(p):
    p.add_argument("--company", nargs="+", help="manufacturer name (e.g. 'Novo Nordisk')")
    p.add_argument("--ingredient", nargs="+", help="medicinal ingredient (e.g. semaglutide)")
    p.add_argument("--brand", nargs="+", help="brand name (e.g. Wegovy)")
    p.add_argument("--submission", nargs="+", choices=SUB_CODES, type=str.upper,
                   help="NDS new drug, SNDS supplement, ANDS generic, SANDS generic supplement")
    p.add_argument("--nas", action="store_true", help="new active substances only")
    p.add_argument("--with-conditions", action="store_true", help="NOC/c (conditional) only")
    p.add_argument("--priority", action="store_true", help="priority review only")
    p.add_argument("--include-admin", action="store_true", help="keep administrative NOCs (name/ownership changes)")
    p.add_argument("--include-veterinary", action="store_true")
    p.add_argument("--since", help="NOC date from YYYY-MM-DD"); p.add_argument("--until", help="NOC date up to YYYY-MM-DD")
    p.add_argument("--days", type=int, help="only NOCs from the last N days")
    p.add_argument("--keyword", help="any word in brand, ingredient, manufacturer, reason or therapeutic class")
    p.add_argument("--max", type=int, default=50)
    p.add_argument("--exclude", nargs="+", help="drop rows mentioning these terms")


def _kw(a):
    return dict(company=a.company, ingredient=a.ingredient, brand=a.brand, submission=a.submission, keyword=a.keyword,
                since=a.since, until=a.until, recent_days=a.days, new_active_substance=a.nas, with_conditions=a.with_conditions,
                priority=a.priority, include_admin=a.include_admin, include_veterinary=a.include_veterinary, exclude=a.exclude)


def main(argv=None):
    p = argparse.ArgumentParser("hcwatch", description="Health Canada Notices of Compliance (Canadian drug approvals). Source: " + SOURCE)
    p.add_argument("--db", default="biowatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="NOCs, newest first"); _q(s); s.add_argument("--json", action="store_true")
    w = sub.add_parser("watch", help="snapshot and diff vs the previous run (new NOCs, suspensions, changed products)")
    w.add_argument("--name", required=True); _q(w); digest.add_args(w)
    c = sub.add_parser("changes"); c.add_argument("--name"); c.add_argument("--since")
    a = p.parse_args(argv)
    if a.cmd == "changes":
        for x in store(a.db).changes(watch=a.name, since=a.since): print(json.dumps(x))
        return
    cl = NOCClient()
    if a.cmd == "watch":
        info = run_watch(cl, store(a.db), a.name, **_kw(a))
        print(f"watch={a.name} run={info['run_id']} nocs={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        digest.emit(a, info["changes_detail"], f"BioCatalystFeed Health Canada NOC: {a.name}")
        for x in info["changes_detail"]: print(f"  {x['kind']:22} {x['old'] or ''} -> {x['new'] or ''}  {x['title'][:90]}")
        print(f"Source: {SOURCE}")
        return
    rows = notices(cl, max_records=a.max, **_kw(a))
    if a.json: print(json.dumps(rows, indent=1)); return
    for r in rows:
        flags = ",".join(f for f, on in (("NAS", r["new_active_substance"]), ("NOC/c", r["with_conditions"]), ("priority", r["priority"])) if on)
        print(f"{r['date']} {r['noc_number']:>6} {r['submission'] or '':5} {flags:16} {'; '.join(r['brand_names'])[:28]:28} "
              f"{'; '.join(r['ingredients'])[:30]:30} {(r['manufacturer'] or '')[:30]:30} {(r['reason'] or '')[:40]}")
    print(f"{len(rows)} rows. Source: {SOURCE}")


if __name__ == "__main__":
    main()
