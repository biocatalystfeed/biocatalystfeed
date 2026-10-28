"""fdawatch CLI."""
from __future__ import annotations
import argparse, json, sys
from .client import OpenFDAClient
from .core import fda_approvals, label_events, company_profile, run_fda_watch
from .report import profile_markdown, approvals_markdown, ATTR
from .store import FDAStore
from .aliases import resolve, table
from biowatch import digest, filters


def main(argv=None):
    p = argparse.ArgumentParser("fdawatch", description="openFDA Drugs@FDA/label monitor + company profiles")
    p.add_argument("--db", default="fdawatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("approvals", help="Drugs@FDA submissions/approvals")
    a_.add_argument("--sponsor"); a_.add_argument("--since"); a_.add_argument("--until"); a_.add_argument("--application")
    a_.add_argument("--novel", action="store_true", help="only original NME/BLA approvals"); a_.add_argument("--md"); a_.add_argument("--json", action="store_true"); digest.add_query_args(a_)
    l = sub.add_parser("labels", help="recent SPL label versions"); l.add_argument("--sponsor"); l.add_argument("--since"); l.add_argument("--max", type=int, default=50)
    c = sub.add_parser("profile", help="trials + FDA for one or more companies")
    c.add_argument("companies", nargs="+"); c.add_argument("--md"); c.add_argument("--json", action="store_true")
    c.add_argument("--days", type=int, default=365); c.add_argument("--include-collaborations", action="store_true")
    c.add_argument("--basic", action="store_true", help="trials + FDA only (skip grants/papers/preprints/SEC)")
    c.add_argument("--no-preprints", action="store_true"); c.add_argument("--no-sec", action="store_true")
    c.add_argument("--preprint-days", type=int, default=14)
    w = sub.add_parser("watch", help="snapshot FDA records and diff vs previous run"); w.add_argument("--name", required=True)
    w.add_argument("--sponsor"); w.add_argument("--since"); digest.add_args(w)
    ch = sub.add_parser("changes"); ch.add_argument("--name"); ch.add_argument("--since")
    al = sub.add_parser("alias", help="show how a name resolves (no args: list table)"); al.add_argument("name", nargs="?")
    a = p.parse_args(argv)
    fc = OpenFDAClient()

    if a.cmd == "approvals":
        rows = fda_approvals(fc, sponsor=a.sponsor, since=a.since, until=a.until, application_number=a.application, novel_only=a.novel)
        rows = filters.exclude(rows, a.exclude, fields=("brand_names", "active_ingredients", "sponsor", "submission_class", "generic_names"))
        if a.rank: rows = filters.rank(rows, a.sponsor, date_field="submission_status_date")
        if a.md: open(a.md, "w").write(approvals_markdown(rows, f"FDA approvals {a.sponsor or ''} {a.since or ''}".strip()))
        if a.json: print(json.dumps(rows, indent=1))
        else:
            for r in rows: print(f"{r['submission_status_date']}  {r['application_number']:10} {r['submission_type']}{r['submission_number']:<4} {(r['sponsor'] or '')[:16]:16} {(r['brand_names'] or '')[:30]:30} {r['submission_class'] or ''}")
            print(f"{len(rows)} submissions", file=sys.stderr)
    elif a.cmd == "labels":
        for x in label_events(fc, sponsor=a.sponsor, since=a.since, max_records=a.max): print(json.dumps(x))
    elif a.cmd == "profile":
        from trialwatch.client import CTGovClient
        ct = CTGovClient()
        kw = {}
        if not a.basic:
            from grantwatch.core import ReporterClient
            from paperwatch.core import PubMedClient, RxivClient
            from secwatch.core import SECClient
            from paperwatch.core import EuropePMCClient
            kw = dict(grant_client=ReporterClient(), pubmed_client=PubMedClient(), preprint_days=a.preprint_days,
                      rxiv_client=None if a.no_preprints else RxivClient(), sec_client=None if a.no_sec else SECClient(),
                      epmc_client=None if a.no_preprints else EuropePMCClient())
        profs = [company_profile(ct, fc, name, recent_days=a.days, include_collaborations=a.include_collaborations, **kw) for name in a.companies]
        if a.md:
            open(a.md, "w").write("# Company profiles\n\n" + "\n".join(profile_markdown(x) for x in profs) + "\n" + ATTR + "\n")
        if a.json or not a.md: print(json.dumps(profs, indent=1))
    elif a.cmd == "watch":
        info = run_fda_watch(fc, FDAStore(a.db), a.name, sponsor=a.sponsor, since=a.since)
        digest.write(info["changes_detail"], f"BioCatalystFeed FDA: {a.name}", a.rss, a.json_feed, getattr(a, "digest_md", None), getattr(a, "digest_html", None))
        print(f"watch={a.name} run={info['run_id']} records={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        for x in info["changes_detail"]: print(f"  {x['key']} {x['kind']:16} {x['field'] or '':22} {x['old']} -> {x['new']}  {x['brand'] or ''}")
    elif a.cmd == "changes":
        for x in FDAStore(a.db).changes(watch=a.name, since=a.since): print(json.dumps(x))
    elif a.cmd == "alias":
        print(json.dumps(resolve(a.name) if a.name else table(), indent=1))


if __name__ == "__main__":
    main()
