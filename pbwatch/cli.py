"""pbwatch CLI: FDA Purple Book licensed biologics, biosimilars and biologic exclusivity (public domain U.S. government data)."""
from __future__ import annotations
import argparse, json
from biowatch import digest
from .core import EXCL_KINDS, SOURCE, TYPES, PurpleBookClient, exclusivities, landscape, products, run_watch, store

CAVEAT = ("FDA lists exclusivity only where it has made a determination (blank is not 'none'); biosimilar launch timing "
          "also depends on patents and settlements.")


def _common(p):
    p.add_argument("--company", nargs="+", help="applicant / license holder (e.g. Amgen)")
    p.add_argument("--keyword", help="any word in proprietary, proper or reference name, or applicant")
    p.add_argument("--max", type=int, default=50)
    p.add_argument("--json", action="store_true")


def _q(p, watch=False):
    p.add_argument("--company", nargs="+", help="applicant / license holder (e.g. Amgen)")
    p.add_argument("--product", nargs="+", help="proprietary or proper name (e.g. Humira, adalimumab)")
    p.add_argument("--reference", nargs="+", help="reference product of biosimilars (e.g. Stelara, ustekinumab)")
    p.add_argument("--type", nargs="+", choices=TYPES, help="351(a) originators, biosimilar (all 351(k)), interchangeable")
    p.add_argument("--application", help="'BLA 761378' or '761378'")
    p.add_argument("--center", choices=("CDER", "CBER"), type=str.upper)
    p.add_argument("--since", help="original approval date from YYYY-MM-DD"); p.add_argument("--until", help="approval date up to YYYY-MM-DD")
    p.add_argument("--days", type=int, help="only BLAs first approved in the last N days")
    p.add_argument("--keyword", help="any word in proprietary, proper or reference name, or applicant")
    p.add_argument("--exclude", nargs="+", help="drop rows mentioning these terms")
    if not watch:
        p.add_argument("--monthly-changes", action="store_true", help="only BLAs FDA flagged new/added/updated in this month's report")
        p.add_argument("--include-revoked", action="store_true", help="keep revoked / voluntarily revoked licenses")
        p.add_argument("--max", type=int, default=50); p.add_argument("--json", action="store_true")


def _kw(a, watch=False):
    kw = dict(company=a.company, name=a.product, reference=a.reference, license_type=a.type, application=a.application,
              center=a.center, since=a.since, until=a.until, recent_days=a.days, keyword=a.keyword, exclude=a.exclude)
    if not watch: kw.update(monthly_changes=a.monthly_changes, include_revoked=a.include_revoked)
    return kw


def main(argv=None):
    p = argparse.ArgumentParser("pbwatch", description="FDA Purple Book: licensed biologics, biosimilars, interchangeables, exclusivity. Source: " + SOURCE)
    p.add_argument("--db", default="biowatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="licensed biologics (one row per BLA), newest approval first"); _q(s)
    x = sub.add_parser("exclusivity", help="reference-product / first-interchangeable / orphan exclusivity expiries, soonest first")
    _common(x); x.add_argument("--product", nargs="+", help="proprietary or proper name")
    x.add_argument("--kind", nargs="+", choices=EXCL_KINDS); x.add_argument("--since", help="expiry from YYYY-MM-DD (default today)")
    x.add_argument("--until", help="expiry up to YYYY-MM-DD"); x.add_argument("--upcoming-days", type=int, help="only expiries within N days")
    x.add_argument("--include-expired", action="store_true"); x.add_argument("--exclude", nargs="+")
    l = sub.add_parser("landscape", help="per reference product: originator BLA, exclusivity expiry, biosimilars and interchangeables (biologic LOE view)")
    _common(l); l.add_argument("--reference", nargs="+", help="reference product (e.g. Stelara, ustekinumab)")
    l.add_argument("--include-unchallenged", action="store_true", help="add originators with a listed exclusivity and no biosimilar yet")
    w = sub.add_parser("watch", help="snapshot and diff vs the previous run (new BLAs, interchangeability, revocations, exclusivity dates)")
    w.add_argument("--name", required=True); _q(w, watch=True)
    digest.add_args(w)
    c = sub.add_parser("changes"); c.add_argument("--name"); c.add_argument("--since")
    a = p.parse_args(argv)
    if a.cmd == "changes":
        for r in store(a.db).changes(watch=a.name, since=a.since): print(json.dumps(r))
        return
    pb = PurpleBookClient()
    if a.cmd == "watch":
        info = run_watch(pb, store(a.db), a.name, **_kw(a, watch=True))
        print(f"watch={a.name} run={info['run_id']} blas={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        digest.emit(a, info["changes_detail"], f"BioCatalystFeed Purple Book: {a.name}")
        for r in info["changes_detail"]: print(f"  {r['kind']:36} {r['old'] or ''} -> {r['new'] or ''}  {r['title'][:90]}")
        print(f"Source: {SOURCE}")
        return
    if a.cmd == "exclusivity":
        rows = exclusivities(pb, company=a.company, name=a.product, kind=a.kind, since=a.since, until=a.until,
                             upcoming_days=a.upcoming_days, include_expired=a.include_expired, keyword=a.keyword,
                             exclude=a.exclude, max_records=a.max)
        if a.json: print(json.dumps(rows, indent=1)); return
        for r in rows:
            print(f"{r['expires']:10} {r['kind']:21} {r['bla']:10} {(r['proprietary_name'] or '')[:24]:24} "
                  f"{(r['proper_name'] or '')[:30]:30} {(r['applicant'] or '')[:30]}")
    elif a.cmd == "landscape":
        rows = landscape(pb, reference=a.reference, company=a.company, keyword=a.keyword,
                         include_unchallenged=a.include_unchallenged, max_records=a.max)
        if a.json: print(json.dumps(rows, indent=1)); return
        for r in rows:
            print(f"{(r['reference_product'] or r['reference_proper_name'])[:28]:28} {r['reference_proper_name'][:22]:22} "
                  f"biosimilars={r['biosimilars']:<3} interchangeable={r['interchangeables']:<3} "
                  f"ref_excl={r['reference_exclusivity_expires'] or '-':10} latest={r['latest_biosimilar_approved'] or '-'}")
    else:
        rows = products(pb, max_records=a.max, **_kw(a))
        if a.json: print(json.dumps(rows, indent=1)); return
        for r in rows:
            kind = "interchangeable" if r["interchangeable"] else "biosimilar" if r["biosimilar"] else "351(a)"
            print(f"{r['approved'] or '?':10} {r['bla']:10} {kind:15} {(r['proprietary_name'] or '')[:22]:22} "
                  f"{(r['proper_name'] or '')[:30]:30} {(r['applicant'] or '')[:26]:26} {r['reference_product'] or ''}"
                  f"{'' if r['licensure'] == 'Licensed' else '  [' + r['licensure'] + ']'}")
    print(f"{len(rows)} rows. {CAVEAT} Source: {SOURCE}")


if __name__ == "__main__":
    main()
