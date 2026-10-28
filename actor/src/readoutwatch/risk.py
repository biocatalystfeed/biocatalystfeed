"""Trials at Risk: trials showing signs of delay or failure to complete, from ClinicalTrials.gov plus local history.

Flags (each with severity 1-3; risk_score = sum, highest first):
  stopped               status SUSPENDED / TERMINATED / WITHDRAWN, record updated within lookback_days (3; why_stopped shown)
  overdue               active trial whose ESTIMATED primary completion date has passed and was not updated to ACTUAL (2)
  stale_overdue         overdue and the record has not been updated for > 365 days (+1)
  delayed               primary completion date moved later between two local snapshots (needs a readouts watch) (2, 3 if > 180 days)
  enrollment_shortfall  ACTUAL enrollment < 80% of the last ESTIMATED enrollment seen in local snapshots (2), or a
                        TERMINATED trial with ACTUAL enrollment < 50% of that estimate (3)
  enrollment_cut        ESTIMATED enrollment target lowered by >= 20% between snapshots (1)
CT.gov's API has no history of past values, so delayed / enrollment_* flags only appear for trials you have snapshotted
(bcf readouts watch / snapshot_readouts); `stopped` and `overdue` work with no history. Not investment advice."""
from __future__ import annotations
import json
from datetime import date, timedelta
from biowatch import provenance as pv
from trialwatch.normalize import normalize
from .core import ACTIVE, DEFAULT_PHASES, fetch, params, resolve_sponsor, store, to_event, today_iso

STOPPED = ("SUSPENDED", "TERMINATED", "WITHDRAWN")


def _days(a, b):
    f = lambda x: date.fromisoformat(x[:10] if len(x) >= 10 else x[:7] + "-01")
    try: return (f(b) - f(a)).days
    except Exception: return None


def history_flags(st, key: str, ev: dict) -> list[dict]:
    """Flags from local snapshot history (readout store) for one record."""
    flags = []
    rows = st.db.execute(f"SELECT field, old, new FROM {st.p}_changes WHERE key=? ORDER BY id", (key,)).fetchall()
    for r in rows:
        if r["field"] == "readout_date" and r["old"] and r["new"] and r["new"] > r["old"]:
            d = _days(r["old"], r["new"]) or 0
            flags.append({"flag": "delayed", "severity": 3 if d > 180 else 2, "detail": f"primary completion moved {r['old']} -> {r['new']} (+{d} days)"})
        if r["field"] == "enrollment" and r["old"] and r["new"]:
            try: o, n = float(r["old"]), float(r["new"])
            except ValueError: continue
            if o and n < 0.8 * o and ev.get("enrollment_type") != "ACTUAL":
                flags.append({"flag": "enrollment_cut", "severity": 1, "detail": f"target enrollment cut {int(o)} -> {int(n)}"})
    est = None
    for (data,) in st.db.execute(f"SELECT data FROM {st.p}_records WHERE key=?", (key,)).fetchall():
        d = json.loads(data)
        if d.get("enrollment_type") == "ESTIMATED" and d.get("enrollment"): est = max(est or 0, d["enrollment"])
    for r in rows:
        if r["field"] == "enrollment" and r["old"]:
            try: est = max(est or 0, int(float(r["old"])))
            except ValueError: pass
    if est and ev.get("enrollment_type") == "ACTUAL" and ev.get("enrollment") is not None and ev["enrollment"] < 0.8 * est:
        sev = 3 if ev.get("status") == "TERMINATED" and ev["enrollment"] < 0.5 * est else 2
        flags.append({"flag": "enrollment_shortfall", "severity": sev, "detail": f"actual enrollment {ev['enrollment']} vs estimated {est} ({ev['enrollment'] * 100 // est}%)"})
    return flags


def trials_at_risk(client, sponsor=None, condition=None, intervention=None, phases=DEFAULT_PHASES, industry_only=True,
                   lookback_days=180, flags=None, db_path=None, max_records=100, sec=None, today=None) -> list[dict]:
    today = today or today_iso()
    as_of = pv.now_utc()
    if sec is not None and not pv._SEC_NAMES: pv.load_sec_tickers(sec)
    qs, _ = resolve_sponsor(sponsor, sec)
    since = (date.fromisoformat(today) - timedelta(days=int(lookback_days))).isoformat()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    st = store(db_path) if db_path else None
    found: dict[str, dict] = {}

    def add(t, fl):
        ev = found.get(t["nct_id"]) or to_event(t, as_of, today)
        ev.setdefault("risk_flags", [])
        ev["risk_flags"] += [f for f in fl if f["flag"] not in {x["flag"] for x in ev["risk_flags"]}]
        found[t["nct_id"]] = ev

    for q in qs:
        # stopped: updated recently (date field = LastUpdatePostDate)
        for s in fetch(client, params(q, condition, intervention, phases, STOPPED, since, today, industry_only, "LastUpdatePostDate"), max_records):
            t = normalize(s)
            add(t, [{"flag": "stopped", "severity": 3, "detail": f"{t['status']}" + (f": {t['why_stopped']}" if t.get("why_stopped") else "")}])
        # overdue: active, primary completion already passed and still ESTIMATED
        for s in fetch(client, params(q, condition, intervention, phases, ACTIVE, since, yesterday, industry_only), max_records):
            t = normalize(s)
            if t.get("primary_completion_type") == "ACTUAL": continue
            fl = [{"flag": "overdue", "severity": 2, "detail": f"estimated primary completion {t['primary_completion_date']} passed; status {t['status']}"}]
            if t.get("last_update_posted") and t["last_update_posted"] < (date.fromisoformat(today) - timedelta(days=365)).isoformat():
                fl.append({"flag": "stale_overdue", "severity": 1, "detail": f"record not updated since {t['last_update_posted']}"})
            add(t, fl)
    if st:  # history-based flags for every snapshotted record (plus those found above)
        keys = {r[0] for r in st.db.execute(f"SELECT DISTINCT key FROM {st.p}_records")}
        for key in keys:
            data = st.db.execute(f"SELECT data FROM {st.p}_records WHERE key=? ORDER BY last_seen DESC", (key,)).fetchone()[0]
            ev0 = json.loads(data)
            ev = found.get(ev0.get("nct_id")) or ev0
            fl = history_flags(st, key, ev)
            if fl:
                if ev0.get("nct_id") not in found:
                    ev = dict(ev0, risk_flags=[]); pv.stamp(ev, ev.get("source_url"), as_of); found[ev0["nct_id"]] = ev
                ev["risk_flags"] += [f for f in fl if f["flag"] not in {x["flag"] for x in ev["risk_flags"]}]
    out = list(found.values())
    if flags: out = [e for e in out if any(f["flag"] in flags for f in e["risk_flags"])]
    for e in out:
        e["risk_score"] = sum(f["severity"] for f in e["risk_flags"])
        e["kind"] = "trial_at_risk"
        pv.stamp(e, e.get("source_url"), as_of)
    out.sort(key=lambda e: (-e["risk_score"], e.get("readout_date") or ""))
    return out[:max_records]
