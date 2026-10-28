"""High-level operations shared by CLI, MCP server and Apify actor."""
from __future__ import annotations
from .client import CTGovClient
from .normalize import normalize
from .store import Store


def sponsor_queries(sponsor: str | None) -> list[str | None]:
    """CT.gov query.spons strings for a sponsor: the raw string first, plus the alias table's ct_queries for a known
    company or ticker (e.g. 'Terns Pharmaceuticals' / 'TERN' -> 'Terns, Inc.', the name CT.gov actually uses).
    A bare ticker is not sent itself (CT.gov free text would match unrelated names, e.g. 'TERN' -> Tern Therapeutics).
    Unknown names are sent as typed."""
    if not sponsor:
        return [sponsor]
    from fdawatch.aliases import resolve, _key
    al = resolve(sponsor)
    out = [sponsor]
    if al.get("known") and al.get("ticker") and _key(sponsor) == _key(al["ticker"]) and al.get("ct_queries"):
        out = []
    if al.get("known"):
        for q in al.get("ct_queries", []):
            if _key(q) not in {_key(x) for x in out}:
                out.append(q)
    return out


def raw_search(client: CTGovClient, max_records=200, sponsor_aliases: bool = True, **q) -> list[dict]:
    """client.search, but a known sponsor is expanded to all of its CT.gov names; results merged by NCT ID, first seen
    wins, capped at max_records."""
    queries = sponsor_queries(q.get("sponsor")) if sponsor_aliases else [q.get("sponsor")]
    if len(queries) == 1:
        return client.search(max_records=max_records, **q)
    seen: set[str] = set(); out: list[dict] = []
    for sq in queries:
        for st in client.search(max_records=max_records, **{**q, "sponsor": sq}):
            nct = (st.get("protocolSection", {}).get("identificationModule", {}) or {}).get("nctId")
            if nct and nct in seen:
                continue
            if nct: seen.add(nct)
            out.append(st)
        if len(out) >= max_records:
            break
    return out[:max_records]


def search(client: CTGovClient, max_records=200, sponsor_aliases: bool = True, **q) -> list[dict]:
    return [normalize(s) for s in raw_search(client, max_records=max_records, sponsor_aliases=sponsor_aliases, **q)]


def run_watch(client: CTGovClient, store: Store, watch: str, max_records=1000, sponsor_aliases: bool = True, **q) -> dict:
    recs = search(client, max_records=max_records, sponsor_aliases=sponsor_aliases, **q)
    info = store.ingest(watch, recs, query=q)
    info["changes_detail"] = store.changes(watch=watch, run_id=info["run_id"])
    info["trials"] = recs
    return info
