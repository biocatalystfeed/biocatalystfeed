"""BioCatalystFeed Apify actor: ClinicalTrials.gov change monitor. On Apify: Actor input/dataset/KV store (snapshot DB
persisted in a named KV store). Locally (no apify SDK or LOCAL=1): reads ./input.json, writes ./storage/output.json.
Self-contained: library code is vendored in ./src (scripts/sync_actor.py). Not pushed anywhere."""
import asyncio, json, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))
from trialwatch.client import CTGovClient  # noqa: E402
from trialwatch.core import run_watch  # noqa: E402
from trialwatch.store import Store  # noqa: E402
from biowatch import filters  # noqa: E402

DISCLAIMER = "Not investment, legal or medical advice. Data may be incomplete, delayed or wrong."


def execute(inp: dict, db_path: str, client=None) -> list[dict]:
    q = dict(sponsor=inp.get("sponsor"), condition=inp.get("condition"), intervention=inp.get("intervention"),
             phases=inp.get("phases"), statuses=inp.get("statuses"), changed_since=inp.get("changedSince"))
    if not any(q.values()): raise ValueError("give at least one of sponsor / condition / intervention / phases / statuses / changedSince")
    info = run_watch(client or CTGovClient(), Store(db_path), inp.get("watchName", "default"), max_records=inp.get("maxRecords", 500), **q)
    trials = filters.exclude(info["trials"], inp.get("excludeTerms"))
    keep = {t["nct_id"] for t in trials}
    if inp.get("outputMode", "changes") == "trials" or info["baseline"]:
        return trials
    return [c for c in info["changes_detail"] if c["nct_id"] in keep]


async def apify_main():
    from apify import Actor
    async with Actor:
        inp = await Actor.get_input() or {}
        kv = await Actor.open_key_value_store(name="biocatalystfeed-state")
        db = os.path.join(tempfile.gettempdir(), "bcf.db")
        blob = await kv.get_value("db")
        if blob: open(db, "wb").write(blob)
        items = execute(inp, db)
        await Actor.push_data(items)
        await kv.set_value("db", open(db, "rb").read(), content_type="application/octet-stream")


def local_main():
    inp = json.load(open(os.path.join(HERE, "input.json")))
    os.makedirs(os.path.join(HERE, "storage"), exist_ok=True)
    items = execute(inp, os.path.join(HERE, "storage", "bcf.db"))
    json.dump(items, open(os.path.join(HERE, "storage", "output.json"), "w"), indent=1)
    print(f"{len(items)} items -> storage/output.json")


if __name__ == "__main__":
    try:
        if os.environ.get("LOCAL"): raise ImportError
        import apify  # noqa: F401
        asyncio.run(apify_main())
    except ImportError:
        local_main()
