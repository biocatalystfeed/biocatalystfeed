"""crlwatch CLI: FDA complete response letters (CRLs) from openFDA (public domain U.S. government data)."""
from __future__ import annotations
import argparse, json
from biowatch import digest
from fdawatch.client import OpenFDAClient
from .core import SOURCE, STATUSES, TOPICS, letters, run_watch, store


def _q(p):
    p.add_argument("--since", help="letter date from YYYY-MM-DD")
    p.add_argument("--until", help="letter date up to YYYY-MM-DD")
    p.add_argument("--company", nargs="+", help="applicant company name (phrase, e.g. 'Regeneron')")
    p.add_argument("--application", help="NDA/BLA number, e.g. 'NDA 218705' or '761308'")
    p.add_argument("--status", nargs="+", choices=STATUSES, help="Approved = application approved since; Unapproved = not (yet) approved")
    p.add_argument("--keyword", help="drug / product name or any word in the letter (local filter)")
    p.add_argument("--topic", nargs="+", choices=TOPICS, help="deficiency topic from the letter's section headings")
    p.add_argument("--max", type=int, default=25)
    digest.add_query_args(p)


def main(argv=None):
    p = argparse.ArgumentParser("crlwatch", description="FDA complete response letters (openFDA). Source: " + SOURCE)
    p.add_argument("--db", default="biowatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="CRLs, newest letter first"); _q(s); s.add_argument("--json", action="store_true")
    s.add_argument("--text", action="store_true", help="with --json: include the full OCR letter text")
    w = sub.add_parser("watch", help="snapshot and diff vs the previous run (new letters, Unapproved -> Approved)")
    w.add_argument("--name", required=True); _q(w); digest.add_args(w)
    c = sub.add_parser("changes"); c.add_argument("--name"); c.add_argument("--since")
    a = p.parse_args(argv)
    if a.cmd == "changes":
        for x in store(a.db).changes(watch=a.name, since=a.since): print(json.dumps(x))
        return
    q = dict(since=a.since, until=a.until, company=a.company, application=a.application, status=a.status,
             keyword=a.keyword, topic=a.topic, exclude=a.exclude, rank=a.rank)
    if a.cmd == "watch":
        info = run_watch(OpenFDAClient(), store(a.db), a.name, **q)
        print(f"watch={a.name} run={info['run_id']} letters={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        digest.write(info["changes_detail"], f"BioCatalystFeed FDA CRLs: {a.name}", a.rss, a.json_feed, getattr(a, "digest_md", None), getattr(a, "digest_html", None))
        for x in info["changes_detail"]: print(f"  {x['kind']:26} {x['old'] or ''} -> {x['new'] or ''}  {x['title'][:80]} {x['url']}")
        print(f"Source: {SOURCE}")
        return
    rows = letters(OpenFDAClient(), max_records=a.max, include_text=a.text and a.json, **q)
    if a.json: print(json.dumps(rows, indent=1)); return
    for r in rows:
        print(f"{r['letter_date'] or '?':10} {(r['application_status'] or ''):10} {(r['applications'] or ''):12} "
              f"{(r['company'] or '')[:34]:34} {(r['product'] or '')[:40]:40} {','.join(r['topics'])[:40]:40} {r['url']}")
    print(f"{len(rows)} letters. Product names and topics are parsed from FDA's redacted OCR text; read the letter. "
          f"Source: {SOURCE}")


if __name__ == "__main__":
    main()
