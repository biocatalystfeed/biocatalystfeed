"""secwatch CLI (prototype): 8-K PDUFA mentions. Output is UNVERIFIED."""
from __future__ import annotations
import argparse, json
from fdawatch.aliases import resolve
from biowatch import digest
from .core import SECClient, pdufa_mentions, run_watch, store, LABEL, not_registered_message


def _cik(c: SECClient, company: str) -> str:
    if company.isdigit(): return company
    al = resolve(company)
    cik = al.get("sec_cik") or (c.ticker_cik(al["ticker"]) if al.get("ticker") else None) or c.ticker_cik(company)
    if not cik: raise SystemExit(not_registered_message(al.get("canonical") or company))
    return cik


def main(argv=None):
    p = argparse.ArgumentParser("secwatch", description="SEC EDGAR 8-K PDUFA-date mentions (UNVERIFIED candidates)")
    p.add_argument("--db", default="biowatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("pdufa"); s.add_argument("company", help="name, ticker or CIK"); s.add_argument("--since"); s.add_argument("--until")
    s.add_argument("--max-docs", type=int, default=15); s.add_argument("--json", action="store_true")
    w = sub.add_parser("watch"); w.add_argument("--name", required=True); w.add_argument("company"); w.add_argument("--since"); digest.add_args(w)
    c = sub.add_parser("changes"); c.add_argument("--name"); c.add_argument("--since")
    a = p.parse_args(argv)
    cl = SECClient()
    if a.cmd == "pdufa":
        rows = pdufa_mentions(cl, _cik(cl, a.company), since=a.since, until=a.until, max_docs=a.max_docs)
        if a.json: print(json.dumps(rows, indent=1)); return
        print(LABEL)
        for r in rows:
            print(f"{r['file_date']} {r['file_type']:8} {r['url']}")
            for x in r["candidates"]:
                print(f"   {'*' if x.get('best') else ' '} {x['date_text']:22} {x.get('date_guess') or ''}  …{x['context'][100:230]}…")
    elif a.cmd == "watch":
        info = run_watch(cl, store(a.db), a.name, _cik(cl, a.company), since=a.since)
        digest.write(info["changes_detail"], f"BioCatalystFeed SEC: {a.name}", a.rss, a.json_feed, getattr(a, "digest_md", None), getattr(a, "digest_html", None))
        print(f"watch={a.name} run={info['run_id']} records={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        for x in info["changes_detail"]: print(f"  {x['kind']:18} {x['old']} -> {x['new']} {x['url']}")
    else:
        for x in store(a.db).changes(watch=a.name, since=a.since): print(json.dumps(x))


if __name__ == "__main__":
    main()
