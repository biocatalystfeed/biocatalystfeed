"""`bcf readouts`: market-wide trial readout calendar, watch + changes, Trials at Risk, digests, static calendar page."""
from __future__ import annotations
import argparse, json, os
from biowatch import digest
from .core import DEFAULT_PHASES, readouts, run_watch, store, today_iso


def _client():
    from trialwatch.client import CTGovClient
    return CTGovClient()


def _sec(a):
    if getattr(a, "no_tickers", False): return None
    from secwatch.core import SECClient
    return SECClient()


def _q(p, window=True):
    p.add_argument("--sponsor", help="sponsor name or ticker (alias-resolved; unknown US tickers via SEC's ticker list)")
    p.add_argument("--condition", help="condition / disease (CT.gov query.cond)")
    p.add_argument("--intervention", help="drug / intervention (CT.gov query.intr)")
    p.add_argument("--phases", nargs="+", default=list(DEFAULT_PHASES), help="default PHASE2 PHASE3; 'any' for all")
    p.add_argument("--all-sponsors", action="store_true", help="include non-industry sponsors (academic, NIH, other)")
    p.add_argument("--no-tickers", action="store_true", help="skip loading SEC's ticker list (alias table only)")
    p.add_argument("--max", type=int, default=200)
    if window:
        p.add_argument("--since", help="readout date from YYYY-MM-DD"); p.add_argument("--until", help="readout date to YYYY-MM-DD")
        p.add_argument("--upcoming", type=int, metavar="DAYS", help="today..today+DAYS (default 90 when no since/until)")
        p.add_argument("--ticker-only", action="store_true", help="only trials whose sponsor matched a ticker")


def _kw(a):
    return dict(sponsor=a.sponsor, condition=a.condition, intervention=a.intervention,
                phases=None if a.phases == ["any"] else a.phases, industry_only=not a.all_sponsors, max_records=a.max)


def _win(a):
    return dict(since=a.since, until=a.until, upcoming_days=a.upcoming, ticker_only=a.ticker_only)


def main(argv=None):
    p = argparse.ArgumentParser("bcf readouts", description="Trial readout calendar (ClinicalTrials.gov primary completion "
                                "dates), Trials at Risk and digests. Not investment advice.")
    p.add_argument("--db", default="biowatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="upcoming readouts, soonest first"); _q(s); s.add_argument("--json", action="store_true")
    for x in ("md", "html", "rss", "json-feed"): s.add_argument(f"--{x}", metavar="FILE", help=f"also write a {x} digest of the results")
    w = sub.add_parser("watch", help="snapshot and diff (new readouts, date slips, ESTIMATED->ACTUAL, status/enrollment)")
    w.add_argument("--name", required=True); _q(w); digest.add_args(w)
    c = sub.add_parser("changes", help="stored changes"); c.add_argument("--name"); c.add_argument("--since")
    r = sub.add_parser("at-risk", help="Trials at Risk: stopped, overdue, delayed, enrollment shortfall"); _q(r, window=False)
    r.add_argument("--lookback", type=int, default=180, help="days back for stopped/overdue (default 180)")
    r.add_argument("--flags", nargs="+", help="keep only these flags (stopped overdue stale_overdue delayed enrollment_shortfall enrollment_cut)")
    r.add_argument("--json", action="store_true")
    for x in ("md", "html", "rss", "json-feed"): r.add_argument(f"--{x}", metavar="FILE", help=f"also write a {x} digest")
    g = sub.add_parser("page", help="write the static calendar page (index.html + calendar.json) for the site"); _q(g)
    g.add_argument("--out", required=True, help="output directory, e.g. ../bcf-site/calendar")
    a = p.parse_args(argv)
    if a.cmd == "changes":
        for x in store(a.db).changes(watch=a.name, since=a.since): print(json.dumps(x))
        return
    if a.cmd == "watch":
        info = run_watch(_client(), store(a.db), a.name, sec=_sec(a), **_kw(a), **_win(a))
        print(f"watch={a.name} run={info['run_id']} readouts={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        digest.write(info["changes_detail"], f"BioCatalystFeed readouts: {a.name}", a.rss, a.json_feed, a.digest_md, a.digest_html)
        for x in info["changes_detail"]: print(f"  {x['kind']:26} {x['old'] or ''} -> {x['new'] or ''} {x.get('direction') or ''} {x['title'][:70]} {x['url']}")
        return
    if a.cmd == "at-risk":
        from .risk import trials_at_risk
        rows = trials_at_risk(_client(), lookback_days=a.lookback, flags=a.flags, db_path=a.db if os.path.exists(a.db) else None,
                              sec=_sec(a), **_kw(a))
        title = "BioCatalystFeed Trials at Risk"
        _digests(a, title, rows)
        if a.json: print(json.dumps(rows, indent=1)); return
        for e in rows:
            print(f"{e['risk_score']:2} {e['nct_id']} {(e.get('ticker') or ''):6} {(e.get('sponsor') or '')[:28]:28} "
                  f"{'; '.join(f['flag'] for f in e['risk_flags']):30} {(e.get('title') or '')[:60]}")
        print(f"{len(rows)} trials at risk. Not investment advice.")
        return
    rows = readouts(_client(), sec=_sec(a), **_kw(a), **_win(a))
    if a.cmd == "page":
        from . import page
        from biowatch.provenance import now_utc
        os.makedirs(a.out, exist_ok=True)
        win = [rows[0]["readout_date"] if rows else today_iso(), rows[-1]["readout_date"] if rows else today_iso()]
        if a.since or a.upcoming is not None or not a.until:
            from .core import _window
            win = list(_window(a.since, a.until, a.upcoming, today_iso()))
        data = page.payload(rows, now_utc(), win, {k: v for k, v in _kw(a).items()})
        open(os.path.join(a.out, "calendar.json"), "w").write(json.dumps(data, separators=(",", ":")))
        open(os.path.join(a.out, "index.html"), "w").write(page.render(data))
        print(f"wrote {a.out}/index.html and calendar.json ({len(rows)} trials)")
        return
    _digests(a, "BioCatalystFeed readout calendar", rows)
    if a.json: print(json.dumps(rows, indent=1)); return
    for e in rows:
        print(f"{e['readout_date'] or '?':10} {'A' if e['readout_date_type'] == 'ACTUAL' else 'E'} {(e['phase'] or ''):13} "
              f"{(e.get('ticker') or ''):6} {(e['sponsor'] or '')[:28]:28} {e['nct_id']} {(e['title'] or '')[:60]}")
    print(f"{len(rows)} readouts (primary completion dates; E = estimated, A = actual). Not investment advice.")


def _digests(a, title, rows):
    if a.md: open(a.md, "w").write(digest.markdown(title, rows))
    if a.html: open(a.html, "w").write(digest.html(title, rows))
    if a.rss: open(a.rss, "w").write(digest.rss(title, rows))
    if a.json_feed: open(a.json_feed, "w").write(json.dumps(digest.json_feed(title, rows), indent=1, default=str))


if __name__ == "__main__":
    main()
