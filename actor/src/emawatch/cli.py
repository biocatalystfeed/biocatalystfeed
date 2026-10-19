"""emawatch CLI (European Medicines Agency medicines data). Output acknowledges EMA as the source, as EMA's reuse terms require."""
from __future__ import annotations
import argparse, json
from biowatch import digest
from .core import EMAClient, SOURCE, search_medicines, run_watch, store

STATUSES = ["Authorised", "Opinion", "Opinion under re-examination", "Refused", "Withdrawn", "Application withdrawn",
            "Withdrawn from rolling review", "Suspended", "Revoked", "Lapsed", "Expired"]


def _q(p):
    p.add_argument("--holder", nargs="+", help="marketing-authorisation holder / applicant (substring, e.g. 'Novo Nordisk')")
    p.add_argument("--drug", nargs="+", help="medicine name, INN or active substance (substring)")
    p.add_argument("--keyword", help="word/phrase in indication, therapeutic area or names (e.g. obesity)")
    p.add_argument("--status", nargs="+", choices=STATUSES, metavar="STATUS", help="EMA medicine status: " + ", ".join(STATUSES))
    p.add_argument("--category", default="Human", help="Human (default) or Veterinary; '' for both")
    p.add_argument("--since", help="latest regulatory event (opinion, EC decision, refusal, withdrawal...) from YYYY-MM-DD")
    p.add_argument("--until"); p.add_argument("--orphan", action="store_true"); p.add_argument("--prime", action="store_true")
    p.add_argument("--max", type=int, default=200)
    digest.add_query_args(p)


def main(argv=None):
    p = argparse.ArgumentParser("emawatch", description="EMA centrally authorised medicines: search + change tracking "
                                "(opinions, EC decisions, refusals, withdrawals). Source: " + SOURCE)
    p.add_argument("--db", default="biowatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); _q(s); s.add_argument("--json", action="store_true")
    w = sub.add_parser("watch"); w.add_argument("--name", required=True); _q(w); digest.add_args(w)
    c = sub.add_parser("changes"); c.add_argument("--name"); c.add_argument("--since")
    a = p.parse_args(argv)
    q = lambda: dict(holder=a.holder, drug=a.drug, keyword=a.keyword, status=a.status, category=a.category or None,
                     since=a.since, until=a.until, orphan=a.orphan, prime=a.prime, exclude=a.exclude, rank=a.rank)
    if a.cmd == "search":
        rows = search_medicines(EMAClient(), max_records=a.max, **q())
        if a.json: print(json.dumps(rows, indent=1)); return
        for r in rows:
            fl = "".join(c for c, f in (("O", "orphan_medicine"), ("P", "prime_priority_medicine"), ("C", "conditional_approval")) if r.get(f))
            print(f"{r['date'] or '':10} {(r['status'] or '')[:22]:22} {fl:3} {(r['name'] or '')[:24]:24} {(r['inn'] or '')[:28]:28} {(r['holder'] or '')[:30]:30} {r['url'] or ''}")
        print(f"{len(rows)} medicines (O=orphan P=PRIME C=conditional). Source: {SOURCE}")
    elif a.cmd == "watch":
        info = run_watch(EMAClient(), store(a.db), a.name, max_records=max(a.max, 2000), **q())
        print(f"watch={a.name} run={info['run_id']} records={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        digest.write(info["changes_detail"], f"BioCatalystFeed EMA: {a.name} (source: {SOURCE})", a.rss, a.json_feed)
        for x in info["changes_detail"]: print(f"  {x['kind']:24} {x['field'] or '':16} {x['old']} -> {x['new']}  {x['title'][:50]} {x['url']}")
        print(f"Source: {SOURCE}")
    else:
        for x in store(a.db).changes(watch=a.name, since=a.since): print(json.dumps(x))


if __name__ == "__main__":
    main()
