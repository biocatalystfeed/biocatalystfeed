"""grantwatch CLI (NIH RePORTER)."""
from __future__ import annotations
import argparse, json
from biowatch import digest
from .core import ReporterClient, search_grants, run_watch, store


def _q(p):
    p.add_argument("--org", nargs="+"); p.add_argument("--org-exact", action="store_true"); p.add_argument("--pi")
    p.add_argument("--keyword"); p.add_argument("--since", help="award notice date from YYYY-MM-DD"); p.add_argument("--until")
    p.add_argument("--fy", nargs="+", type=int, dest="fiscal_years"); p.add_argument("--max", type=int, default=200)
    p.add_argument("--pi-exact", action="store_true", help="PI must match first, middle initial and last name exactly")
    p.add_argument("--no-future", action="store_true", help="drop grants whose award notice date is after today")
    p.add_argument("--sort", choices=["award_notice_date", "fiscal_year", "award_amount", "relevance"], default="award_notice_date")
    digest.add_query_args(p)


def main(argv=None):
    p = argparse.ArgumentParser("grantwatch", description="NIH RePORTER grant search + new-award tracking")
    p.add_argument("--db", default="biowatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); _q(s); s.add_argument("--json", action="store_true")
    w = sub.add_parser("watch"); w.add_argument("--name", required=True); _q(w); digest.add_args(w)
    c = sub.add_parser("changes"); c.add_argument("--name"); c.add_argument("--since")
    a = p.parse_args(argv)
    q = lambda: dict(org=a.org, org_exact=a.org_exact, pi=a.pi, keyword=a.keyword, since=a.since, until=a.until, fiscal_years=a.fiscal_years,
                     pi_exact=a.pi_exact, exclude=a.exclude, rank=a.rank, include_future=not a.no_future, sort=a.sort)
    if a.cmd == "search":
        rows = search_grants(ReporterClient(), max_records=a.max, **q())
        if a.json: print(json.dumps(rows, indent=1)); return
        for r in rows: print(f"{'~' if r.get('future_dated') else ' '}{r['award_notice_date'] or '':10} FY{r['fiscal_year']} {r['project_num'] or '':22} {(r['org_name'] or '')[:28]:28} {(r['pis'] or '')[:24]:24} ${r['award_amount'] or 0:>10,} {(r['title'] or '')[:60]}")
        print(f"{len(rows)} grants" + ("  (~ = award notice date in the future)" if any(r.get("future_dated") for r in rows) else ""))
    elif a.cmd == "watch":
        info = run_watch(ReporterClient(), store(a.db), a.name, max_records=a.max, **q())
        print(f"watch={a.name} run={info['run_id']} records={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        digest.write(info["changes_detail"], f"BioCatalystFeed grants: {a.name}", a.rss, a.json_feed, getattr(a, "digest_md", None), getattr(a, "digest_html", None))
        for x in info["changes_detail"]: print(f"  {x['kind']:20} {x['field'] or '':16} {x['old']} -> {x['new']}  {x['title'][:60]} {x['url']}")
    else:
        for x in store(a.db).changes(watch=a.name, since=a.since): print(json.dumps(x))


if __name__ == "__main__":
    main()
