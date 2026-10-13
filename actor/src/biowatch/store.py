"""Generic snapshot/diff store. Each record needs a stable 'key'; `tracked` lists fields whose changes are logged.
Tables are prefixed per tool (grant_*, paper_*, sec_*) so everything can share the trialwatch DB file."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone


class ItemStore:
    def __init__(self, path: str, prefix: str, tracked: tuple[str, ...], new_kind: str = "new_item"):
        self.p, self.tracked, self.new_kind = prefix, tracked, new_kind
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        p = prefix
        self.db.executescript(f"""
CREATE TABLE IF NOT EXISTS {p}_records (watch TEXT, key TEXT, data TEXT, first_seen TEXT, last_seen TEXT, PRIMARY KEY (watch, key));
CREATE TABLE IF NOT EXISTS {p}_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, watch TEXT, ran_at TEXT, query TEXT, n INTEGER);
CREATE TABLE IF NOT EXISTS {p}_changes (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, watch TEXT, key TEXT, kind TEXT,
  field TEXT, old TEXT, new TEXT, title TEXT, url TEXT, detected_at TEXT);
CREATE INDEX IF NOT EXISTS ix_{p}_changes ON {p}_changes(watch, detected_at);""")

    def ingest(self, watch: str, rows: list[dict], query: dict | None = None, now: str | None = None) -> dict:
        now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
        p = self.p
        first = not self.db.execute(f"SELECT 1 FROM {p}_runs WHERE watch=?", (watch,)).fetchone()
        run_id = self.db.execute(f"INSERT INTO {p}_runs(watch, ran_at, query, n) VALUES (?,?,?,?)",
                                 (watch, now, json.dumps(query or {}), len(rows))).lastrowid
        ch = []
        for r in rows:
            old = self.db.execute(f"SELECT data FROM {p}_records WHERE watch=? AND key=?", (watch, r["key"])).fetchone()
            if old is None:
                if not first: ch.append((r, self.new_kind, None, None, None))
                self.db.execute(f"INSERT INTO {p}_records VALUES (?,?,?,?,?)", (watch, r["key"], json.dumps(r), now, now))
            else:
                o = json.loads(old["data"])
                ch += [(r, f + "_change", f, o.get(f), r.get(f)) for f in self.tracked if o.get(f) != r.get(f)]
                self.db.execute(f"UPDATE {p}_records SET data=?, last_seen=? WHERE watch=? AND key=?", (json.dumps(r), now, watch, r["key"]))
        for r, kind, f, o, n in ch:
            self.db.execute(f"INSERT INTO {p}_changes(run_id, watch, key, kind, field, old, new, title, url, detected_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (run_id, watch, r["key"], kind, f, None if o is None else str(o), None if n is None else str(n),
                             (r.get("title") or "")[:300], r.get("url"), now))
        self.db.commit()
        return {"run_id": run_id, "baseline": first, "records": len(rows), "changes": len(ch)}

    def changes(self, watch: str | None = None, since: str | None = None, run_id: int | None = None) -> list[dict]:
        q, a = f"SELECT * FROM {self.p}_changes WHERE 1=1", []
        if watch: q += " AND watch=?"; a.append(watch)
        if since: q += " AND detected_at>=?"; a.append(since)
        if run_id: q += " AND run_id=?"; a.append(run_id)
        return [dict(r) for r in self.db.execute(q + " ORDER BY id", a)]
