"""paperwatch CLI (PubMed + Europe PMC + bioRxiv/medRxiv preprints)."""
from __future__ import annotations
import argparse, json
from biowatch import digest, globalcov as gc
from trialwatch.cli import add_global_args, maybe_tip
from .core import PubMedClient, RxivClient, EuropePMCClient, search_all, run_watch, store

SOURCES = ("pubmed", "europepmc", "preprints")


def _q(p):
    p.add_argument("--affiliation", nargs="+"); p.add_argument("--drug", nargs="+"); p.add_argument("--keyword")
    p.add_argument("--since", help="publication date (the date shown) from YYYY-MM-DD; Europe PMC uses first-publication date"); p.add_argument("--max", type=int, default=100)
    p.add_argument("--sources", nargs="+", choices=SOURCES, default=["pubmed", "europepmc", "preprints"],
                   help="which sources to query (default: all; results are deduped by DOI/PMID)")
    p.add_argument("--preprint-days", type=int, default=14); p.add_argument("--no-preprints", action="store_true")
    p.add_argument("--rxiv-api", action="store_true", help="fetch preprints from the (slow) bioRxiv API instead of Europe PMC")
    digest.add_query_args(p)


def _clients(a):
    src = set(a.sources) - ({"preprints"} if a.no_preprints else set())
    pm = PubMedClient() if "pubmed" in src else None
    want_pre = "preprints" in src
    epmc = EuropePMCClient() if ("europepmc" in src or (want_pre and not a.rxiv_api)) else None
    rx = RxivClient() if want_pre else None  # bioRxiv API: primary with --rxiv-api, else fallback only
    return pm, epmc, rx, src


def main(argv=None):
    p = argparse.ArgumentParser("paperwatch", description="PubMed + Europe PMC + bioRxiv/medRxiv metadata search with new-item tracking")
    p.add_argument("--db", default="biowatch.db")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); _q(s); s.add_argument("--json", action="store_true"); add_global_args(s)
    w = sub.add_parser("watch"); w.add_argument("--name", required=True); _q(w); digest.add_args(w)
    c = sub.add_parser("changes"); c.add_argument("--name"); c.add_argument("--since"); digest.add_args(c)
    a = p.parse_args(argv)
    if a.cmd in ("search", "watch"):
        pm, epmc, rx, src = _clients(a)
    if a.cmd == "search":
        res = _search(a, pm, epmc, rx, src)
        any_global = False
        if a.use_global:
            gc.parse_sources(a.global_sources)  # validates; papers flagging does not depend on registry sources
            try:
                affs = gc.lookup_affiliations(epmc or EuropePMCClient(), res["papers"])
            except Exception as e:
                affs = {}; res["errors"]["global_affiliations"] = f"{type(e).__name__}: {e}"
            gc.annotate_papers(res["papers"], affs)
            any_global = any(gc.is_global(r) for r in res["papers"])
            if any_global: res["global_disclaimer"] = gc.GLOBAL_DISCLAIMER
        if a.json: print(json.dumps(res, indent=1)); return
        if a.use_global: print(gc.HEADER)
        for k in ("pubmed", "europepmc"):
            if res.get(k): print(f"{k}: {res[k]['total']} total")
        for k, e in res["errors"].items(): print(f"! {k} failed: {e}")
        for r in res["papers"]:
            rel = f"{r['relevance']:>4.0f} " if "relevance" in r else ""
            lab = (gc.text_label(r) + " ") if a.use_global and gc.text_label(r) else ""
            print(f"{lab}{rel}{r['date'] or '':10} {'+'.join(x for x in r['sources'] if x):18} {(r['title'] or '')[:90]:90} {r['url']}")
        if any_global: print(gc.GLOBAL_DISCLAIMER)
        print(f"{len(res['papers'])} unique papers")
        if not a.use_global: maybe_tip(a)
    elif a.cmd == "watch":
        info = run_watch(pm, rx, store(a.db), a.name, a.affiliation, a.drug, a.keyword, since=a.since,
                         preprint_days=a.preprint_days if "preprints" in src else 0, max_records=a.max, epmc=epmc,
                         exclude=a.exclude, epmc_journals="europepmc" in src, preprints_via_epmc=not a.rxiv_api)
        digest.write(info["changes_detail"], f"BioCatalystFeed papers: {a.name}", a.rss, a.json_feed)
        print(f"watch={a.name} run={info['run_id']} records={info['records']} changes={info['changes']}{' (baseline)' if info['baseline'] else ''}")
        for x in info["changes_detail"]: print(f"  {x['kind']:14} {x['field'] or '':10} {x['title'][:80]} {x['url']}")
    else:
        ch = store(a.db).changes(watch=a.name, since=a.since)
        digest.write(ch, f"BioCatalystFeed papers: {a.name or 'all'}", a.rss, a.json_feed)
        for x in ch: print(json.dumps(x))


def _search(a, pm, epmc, rx, src):
    pre_days = a.preprint_days if "preprints" in src else 0
    use_epmc_journals = epmc if "europepmc" in src else None
    res = search_all(pm, use_epmc_journals, None, a.affiliation, a.drug, a.keyword, since=a.since, preprint_days=0,
                     max_records=a.max, exclude=a.exclude, rank=a.rank)
    if pre_days:
        from .core import search_preprints_fast, combined
        try:
            pre = search_preprints_fast(None if a.rxiv_api else epmc, rx, a.affiliation, a.drug, a.keyword, days=pre_days, max_records=a.max)
        except Exception as e:
            pre = []; res["errors"]["preprints"] = f"{type(e).__name__}: {e}"
        res["preprints"] = [x["key"] for x in pre]
        res["papers"] = combined(res["papers"] + pre, (a.affiliation, a.drug, a.keyword), a.exclude, a.rank)
    return res


if __name__ == "__main__":
    main()
