"""adcomwatch CLI: FDA advisory committee meeting notices from the Federal Register (public domain U.S. government data)."""
from __future__ import annotations
import argparse, json
from datetime import date, timedelta
from biowatch import digest
from .core import AREAS, SOURCE, FRClient, meetings, run_watch, store


def _q(p):
    p.add_argument("--since", help="notice publication date from YYYY-MM-DD (default: 365 days ago)")
    p.add_argument("--until", help="notice publication date up to YYYY-MM-DD")
    p.add_argument("--area", nargs="+", choices=AREAS, help="committee area (default: all except tobacco)")
    p.add_argument("--committee", help="committee name substring, e.g. 'Oncologic Drugs'")
    p.add_argument("--keyword", help="word/phrase in the title, agenda or sponsor (e.g. a drug or company name)")
    p.add_argument("--upcoming", action="store_true", help="only meetings dated today or later")
    p.add_argument("--no-agenda", action="store_true", help="skip fetching each notice's full text (faster; no agenda/NDA/sponsor)")
    p.add_argument("--max", type=int, default=50)
    digest.add_query_args(p)


def main(argv=None):
    p = argparse.ArgumentParser("adcomwatch", description="FDA advisory committee meetings (Federal Register notices). Source: " + SOURCE)
    p.add_argument("--db", default="biowatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="meeting notices, newest meeting first"); _q(s); s.add_argument("--json", action="store_true")
    u = sub.add_parser("upcoming", help="shortcut for search --upcoming"); _q(u); u.add_argument("--json", action="store_true")
    w = sub.add_parser("watch", help="snapshot and diff vs the previous run"); w.add_argument("--name", required=True); _q(w); digest.add_args(w)
    c = sub.add_parser("changes"); c.add_argument("--name"); c.add_argument("--since")
    a = p.parse_args(argv)
    if a.cmd == "changes":
        for x in store(a.db).changes(watch=a.name, since=a.since): print(json.dumps(x))
        return
    q = dict(since=a.since or (date.today() - timedelta(days=365)).isoformat(), until=a.until, area=a.area,
             committee=a.committee, keyword=a.keyword, upcoming=a.upcoming or a.cmd == "upcoming",
             agenda=not a.no_agenda, exclude=a.exclude, rank=a.rank)
    if a.cmd == "watch":
        info = run_watch(FRClient(), store(a.db), a.name, **q)
        print(f"watch={a.name} run={info['run_id']} notices={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        digest.write(info["changes_detail"], f"BioCatalystFeed FDA AdComs: {a.name}", a.rss, a.json_feed)
        for x in info["changes_detail"]: print(f"  {x['kind']:20} {x['field'] or '':14} {x['old']} -> {x['new']}  {x['title'][:60]} {x['url']}")
        print(f"Source: {SOURCE}")
        return
    rows = meetings(FRClient(), max_records=a.max, **q)
    if a.json: print(json.dumps(rows, indent=1)); return
    for r in rows:
        what = r["applications"] or ""
        if r["sponsors"]: what += f" ({r['sponsors']})"
        print(f"{r['meeting_date'] or '?':10} {r['kind']:12} {r['area']:9} {r['committee'][:55]:55} {what[:70]:70} {r['url']}")
    print(f"{len(rows)} notices. Meeting dates and agendas are parsed from the notice text; check the notice and fda.gov "
          f"for changes. Source: {SOURCE}")


if __name__ == "__main__":
    main()
