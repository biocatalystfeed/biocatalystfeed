"""High-level operations shared by CLI, MCP server and Apify actor."""
from __future__ import annotations
from .client import CTGovClient
from .normalize import normalize
from .store import Store


def search(client: CTGovClient, max_records=200, **q) -> list[dict]:
    return [normalize(s) for s in client.search(max_records=max_records, **q)]


def run_watch(client: CTGovClient, store: Store, watch: str, max_records=1000, **q) -> dict:
    recs = search(client, max_records=max_records, **q)
    info = store.ingest(watch, recs, query=q)
    info["changes_detail"] = store.changes(watch=watch, run_id=info["run_id"])
    info["trials"] = recs
    return info
