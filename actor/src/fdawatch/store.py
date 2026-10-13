"""SQLite change tracking for FDA submissions and labels (same pattern as trialwatch.store; own tables, can share the DB file)."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from .normalize import SUB_TRACKED, LABEL_TRACKED

SCHEMA = """
CREATE TABLE IF NOT EXISTS fda_records (watch TEXT, kind TEXT, key TEXT, data TEXT, first_seen TEXT, last_seen TEXT,
  PRIMARY KEY (watch, kind, key));
CREATE TABLE IF NOT EXISTS fda_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, watch TEXT, ran_at TEXT, query TEXT, n INTEGER);
CREATE TABLE IF NOT EXISTS fda_changes (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, watch TEXT, rec_kind TEXT,
  key TEXT, kind TEXT, field TEXT, old TEXT, new TEXT, detected_at TEXT);
CREATE INDEX IF NOT EXISTS ix_fda_changes ON fda_changes(watch, detected_at);
"""
TRACKED = {"submission": SUB_TRACKED, "label": LABEL_TRACKED}


def classify(rec_kind: str, field: str, old, new) -> str:
    if rec_kind == "submission" and field == "submission_status":
        return "approval" if new == "APPROVED" else "status_change"
    if rec_kind == "label" and field == "version": return "label_revision"
    if field == "n_docs": return "new_documents"
    return "date_change" if "date" in field or field == "effective_time" else "field_change"


def diff(rec_kind: str, old: dict, new: dict) -> list[tuple]:
    return [(classify(rec_kind, f, old.get(f), new.get(f)), f, old.get(f), new.get(f))
            for f in TRACKED[rec_kind] if old.get(f) != new.get(f)]


class FDAStore:
    def __init__(self, path: str = "fdawatch.db"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def ingest(self, watch: str, submissions: list[dict], labels: list[dict] = (), query: dict | None = None,
               now: str | None = None) -> dict:
        now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
        first = not self.db.execute("SELECT 1 FROM fda_runs WHERE watch=?", (watch,)).fetchone()
        run_id = self.db.execute("INSERT INTO fda_runs(watch, ran_at, query, n) VALUES (?,?,?,?)",
                                 (watch, now, json.dumps(query or {}), len(submissions) + len(labels))).lastrowid
        ch = []
        for rk, rows in (("submission", submissions), ("label", labels)):
            for r in rows:
                old = self.db.execute("SELECT data FROM fda_records WHERE watch=? AND kind=? AND key=?", (watch, rk, r["key"])).fetchone()
                if old is None:
                    if not first:
                        kind = "new_submission" if rk == "submission" else "new_label"
                        ch.append((rk, r["key"], kind, None, None, r.get("submission_status") or r.get("version")))
                    self.db.execute("INSERT INTO fda_records VALUES (?,?,?,?,?,?)", (watch, rk, r["key"], json.dumps(r), now, now))
                else:
                    for kind, f, o, n in diff(rk, json.loads(old["data"]), r):
                        ch.append((rk, r["key"], kind, f, o, n))
                    self.db.execute("UPDATE fda_records SET data=?, last_seen=? WHERE watch=? AND kind=? AND key=?",
                                    (json.dumps(r), now, watch, rk, r["key"]))
        for rk, key, kind, f, o, n in ch:
            self.db.execute("INSERT INTO fda_changes(run_id, watch, rec_kind, key, kind, field, old, new, detected_at) VALUES (?,?,?,?,?,?,?,?,?)",
                            (run_id, watch, rk, key, kind, f, None if o is None else str(o), None if n is None else str(n), now))
        self.db.commit()
        return {"run_id": run_id, "baseline": first, "records": len(submissions) + len(labels), "changes": len(ch)}

    def changes(self, watch: str | None = None, since: str | None = None, run_id: int | None = None) -> list[dict]:
        q = ("SELECT c.*, COALESCE(json_extract(r.data,'$.brand_names'), json_extract(r.data,'$.brand_name')) brand "
             "FROM fda_changes c LEFT JOIN fda_records r ON r.watch=c.watch AND r.kind=c.rec_kind AND r.key=c.key WHERE 1=1")
        a: list = []
        if watch: q += " AND c.watch=?"; a.append(watch)
        if since: q += " AND c.detected_at>=?"; a.append(since)
        if run_id: q += " AND c.run_id=?"; a.append(run_id)
        return [dict(r) for r in self.db.execute(q + " ORDER BY c.id", a)]
