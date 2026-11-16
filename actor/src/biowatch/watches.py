"""List the saved watches in a local snapshot DB (read-only): which named queries exist, for which tool, how many runs,
first/last run time, records in the last run, stored change count and the query that was saved. Lets an agent discover
existing watches before calling a snapshot_* or *_changes_since tool."""
from __future__ import annotations
import json, os, sqlite3

# table prefix -> (tool name used by changes_feed / CLI, snapshot tool, changes tool)
TOOLS = {
    "": ("trials", "snapshot_watch", "trial_changes_since"),
    "fda": ("fda", "bcf fda watch (CLI)", "fda_changes_since"),
    "grant": ("grants", "snapshot_grants", "grant_changes_since"),
    "paper": ("papers", "snapshot_papers", "paper_changes_since"),
    "sec": ("sec", "bcf sec watch (CLI)", "changes_feed(tool='sec')"),
    "ema": ("ema", "snapshot_ema", "ema_changes_since"),
    "adcom": ("adcom", "snapshot_adcom", "adcom_changes_since"),
    "crl": ("crl", "snapshot_crl", "crl_changes_since"),
    "ob": ("orange-book", "snapshot_orange_book", "orange_book_changes_since"),
    "hcnoc": ("health-canada", "snapshot_health_canada", "health_canada_changes_since"),
    "pb": ("purple-book", "snapshot_purple_book", "purple_book_changes_since"),
    "fdadec": ("fda-decisions", "snapshot_fda_decisions", "fda_decision_changes_since"),
    "readout": ("readouts", "snapshot_readouts", "readout_changes_since"),
}


def list_watches(db_path: str, tool: str | None = None) -> list[dict]:
    """One row per (tool, watch), newest last run first. A missing DB returns []. Opens the DB read-only."""
    if not os.path.exists(db_path): return []
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        out = []
        for prefix, (name, snap, chg) in TOOLS.items():
            if tool and tool != name: continue
            runs, changes = (f"{prefix}_runs", f"{prefix}_changes") if prefix else ("runs", "changes")
            if runs not in tables: continue
            for r in db.execute(f"SELECT watch, COUNT(*) n_runs, MIN(ran_at) first_run, MAX(ran_at) last_run, MAX(id) last_id "
                                f"FROM {runs} GROUP BY watch"):
                last = db.execute(f"SELECT n, query FROM {runs} WHERE id=?", (r["last_id"],)).fetchone()
                n_ch = db.execute(f"SELECT COUNT(*) FROM {changes} WHERE watch=?", (r["watch"],)).fetchone()[0] if changes in tables else 0
                try:
                    q = json.loads(last["query"] or "{}")
                except ValueError:
                    q = {"raw": last["query"]}
                out.append({"tool": name, "watch": r["watch"], "runs": r["n_runs"], "first_run": r["first_run"],
                            "last_run": r["last_run"], "last_run_records": last["n"], "changes_stored": n_ch,
                            "query": {k: v for k, v in q.items() if v not in (None, [], {}, "")},
                            "snapshot_tool": snap, "changes_tool": chg})
        out.sort(key=lambda x: x["last_run"] or "", reverse=True)
        return out
    finally:
        db.close()
