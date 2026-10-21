"""SQLite snapshot store + diff engine."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from .normalize import TRACKED, ADDED_0_3
from .severity import annotate, at_least, LEVELS

SCHEMA = """
CREATE TABLE IF NOT EXISTS trials (watch TEXT, nct_id TEXT, data TEXT, first_seen TEXT, last_seen TEXT,
  PRIMARY KEY (watch, nct_id));
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, watch TEXT, ran_at TEXT, query TEXT, n INTEGER);
CREATE TABLE IF NOT EXISTS changes (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, watch TEXT, nct_id TEXT,
  kind TEXT, field TEXT, old TEXT, new TEXT, detected_at TEXT);
CREATE INDEX IF NOT EXISTS ix_changes ON changes(watch, detected_at);
"""


KINDS = {"status": "status_change", "phase": "phase_change", "enrollment": "enrollment_change",
         "primary_outcomes": "endpoint_change", "arm_count": "arm_change", "site_count": "site_change",
         "interventions": "intervention_change", "results_first_posted": "results_posted"}


def classify(field: str) -> str:
    return KINDS.get(field, "date_change" if field.endswith("date") else "field_change")


def diff_records(old: dict, new: dict) -> list[tuple[str, str, object, object]]:
    out = []
    for f in TRACKED:
        if f in ADDED_0_3 and f not in old:
            continue  # snapshot from an older version: no baseline for this field yet
        if old.get(f) != new.get(f):
            out.append((classify(f), f, old.get(f), new.get(f)))
    return out


class Store:
    def __init__(self, path: str = "trialwatch.db"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def ingest(self, watch: str, records: list[dict], query: dict | None = None, now: str | None = None) -> dict:
        now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
        first_run = not self.db.execute("SELECT 1 FROM runs WHERE watch=?", (watch,)).fetchone()
        cur = self.db.execute("INSERT INTO runs(watch, ran_at, query, n) VALUES (?,?,?,?)",
                              (watch, now, json.dumps(query or {}), len(records)))
        run_id = cur.lastrowid
        changes = []
        for r in records:
            row = self.db.execute("SELECT data FROM trials WHERE watch=? AND nct_id=?", (watch, r["nct_id"])).fetchone()
            if row is None:
                if not first_run:
                    changes.append((r["nct_id"], "new_trial", None, None, r.get("status")))
                self.db.execute("INSERT INTO trials VALUES (?,?,?,?,?)", (watch, r["nct_id"], json.dumps(r), now, now))
            else:
                for kind, f, o, n in diff_records(json.loads(row["data"]), r):
                    changes.append((r["nct_id"], kind, f, o, n))
                self.db.execute("UPDATE trials SET data=?, last_seen=? WHERE watch=? AND nct_id=?",
                                (json.dumps(r), now, watch, r["nct_id"]))
        for nct, kind, f, o, n in changes:
            self.db.execute("INSERT INTO changes(run_id, watch, nct_id, kind, field, old, new, detected_at) VALUES (?,?,?,?,?,?,?,?)",
                            (run_id, watch, nct, kind, f, None if o is None else str(o), None if n is None else str(n), now))
        self.db.commit()
        return {"run_id": run_id, "baseline": first_run, "records": len(records), "changes": len(changes)}

    def changes(self, watch: str | None = None, since: str | None = None, run_id: int | None = None,
                min_severity: str | None = None) -> list[dict]:
        """Detected changes, oldest first, each with a `severity` (critical / notable / minor) and, for date fields,
        `shift_days`. min_severity drops lower levels."""
        q, a = "SELECT c.*, json_extract(t.data,'$.title') title, json_extract(t.data,'$.lead_sponsor') sponsor FROM changes c LEFT JOIN trials t ON t.watch=c.watch AND t.nct_id=c.nct_id WHERE 1=1", []
        if watch: q += " AND c.watch=?"; a.append(watch)
        if since: q += " AND c.detected_at>=?"; a.append(since)
        if run_id: q += " AND c.run_id=?"; a.append(run_id)
        return at_least(annotate([dict(r) for r in self.db.execute(q + " ORDER BY c.id", a)]), min_severity)

    def trials(self, watch: str) -> list[dict]:
        return [json.loads(r["data"]) for r in self.db.execute("SELECT data FROM trials WHERE watch=? ORDER BY nct_id", (watch,))]
