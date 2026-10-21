"""trialwatch CLI."""
from __future__ import annotations
import argparse, json, sys
from .client import CTGovClient
from .core import search, run_watch
from .normalize import normalize
from .report import markdown, write_csv, sponsor_pipeline
from .store import Store
from .severity import at_least
from biowatch import digest, filters


def _short(v, n=80):
    v = "" if v is None else str(v)
    return v if len(v) <= n else v[:n - 1] + "…"


def _q(a):
    return dict(sponsor=a.sponsor, condition=a.condition, intervention=a.intervention, term=a.term,
                phases=a.phase, statuses=a.status, changed_since=a.changed_since)


def main(argv=None):
    p = argparse.ArgumentParser("trialwatch", description="Monitor ClinicalTrials.gov (API v2)")
    p.add_argument("--db", default="trialwatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)

    def qargs(sp):
        sp.add_argument("--sponsor"); sp.add_argument("--condition"); sp.add_argument("--intervention")
        sp.add_argument("--term"); sp.add_argument("--phase", nargs="*"); sp.add_argument("--status", nargs="*")
        sp.add_argument("--changed-since", help="YYYY-MM-DD (LastUpdatePostDate)")
        sp.add_argument("--max", type=int, default=200); digest.add_query_args(sp)
    s = sub.add_parser("search"); qargs(s); s.add_argument("--csv"); s.add_argument("--json", action="store_true")
    w = sub.add_parser("watch", help="snapshot a query and diff vs previous run"); qargs(w)
    sev = dict(choices=["minor", "notable", "critical"], help="only show/report changes at or above this severity")
    digest.add_args(w); w.add_argument("--min-severity", **sev); w.add_argument("--name", required=True); w.add_argument("--md"); w.add_argument("--csv"); w.add_argument("--changes-csv")
    g = sub.add_parser("get"); g.add_argument("nct_id")
    c = sub.add_parser("changes"); c.add_argument("--name"); c.add_argument("--since"); c.add_argument("--min-severity", **sev); c.add_argument("--json", action="store_true", help="one JSON object per line (previous default)")
    pp = sub.add_parser("pipeline"); pp.add_argument("sponsor"); pp.add_argument("--max", type=int, default=500)
    a = p.parse_args(argv)
    cl = CTGovClient()

    if a.cmd == "search":
        recs = filters.exclude(search(cl, max_records=a.max, **_q(a)), a.exclude)
        if a.rank: recs = filters.rank(recs, a.term, a.condition, a.intervention, date_field="last_update_posted")
        if a.csv: write_csv(a.csv, recs)
        if a.json: print(json.dumps(recs, indent=1))
        else:
            for r in recs: print(f"{r['nct_id']}  {r['phase'] or '-':14} {r['status']:24} {r['lead_sponsor'][:30]:30} {(r['title'] or '')[:70]}")
            print(f"{len(recs)} trials", file=sys.stderr)
    elif a.cmd == "watch":
        st = Store(a.db)
        info = run_watch(cl, st, a.name, max_records=a.max, **_q(a))
        if a.exclude:  # exclusion applies to reporting; the snapshot keeps the full query result
            drop = {r["nct_id"] for r in info["trials"]} - {r["nct_id"] for r in filters.exclude(info["trials"], a.exclude)}
            info["trials"] = [r for r in info["trials"] if r["nct_id"] not in drop]
            info["changes_detail"] = [c for c in info["changes_detail"] if c["nct_id"] not in drop]
        ch = at_least(info["changes_detail"], a.min_severity)
        digest.write(ch, f"BioCatalystFeed trials: {a.name}", a.rss, a.json_feed)
        print(f"watch={a.name} run={info['run_id']} trials={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        for x in ch:
            sd = f" ({x['shift_days']:+d} days)" if x.get("shift_days") is not None else ""
            print(f"  {x['severity']:8} {x['nct_id']} {x['kind']:19} {x['field'] or '':24} {_short(x['old'])} -> {_short(x['new'])}{sd}")
        if a.md:
            open(a.md, "w").write(markdown(f"trialwatch: {a.name}", info["trials"], ch, f"Run {info['run_id']}; query `{json.dumps(_q(a))}`"))
        if a.csv: write_csv(a.csv, info["trials"])
        if a.changes_csv and ch: write_csv(a.changes_csv, ch)
    elif a.cmd == "get":
        print(json.dumps(normalize(cl.get(a.nct_id)), indent=1))
    elif a.cmd == "changes":
        chs = Store(a.db).changes(watch=a.name, since=a.since, min_severity=a.min_severity)
        if a.json:
            for x in chs: print(json.dumps(x))
        else:
            for x in chs:
                sd = f" ({x['shift_days']:+d} days)" if x.get("shift_days") is not None else ""
                print(f"{(x.get('detected_at') or '')[:10]} {x.get('watch') or '':12} {x.get('severity') or '':8} {x['nct_id']} {x.get('kind') or '':19} {x.get('field') or '':24} {_short(x.get('old'))} -> {_short(x.get('new'))}{sd}")
            print(f"{len(chs)} changes", file=sys.stderr)
    elif a.cmd == "pipeline":
        print(json.dumps(sponsor_pipeline(search(cl, sponsor=a.sponsor, max_records=a.max)), indent=1))


if __name__ == "__main__":
    main()
