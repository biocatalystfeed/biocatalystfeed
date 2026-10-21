"""Severity labels for detected trial changes: critical / notable / minor.

Rules (deterministic, documented in the README):
- critical: status moves to TERMINATED, SUSPENDED or WITHDRAWN; a why-stopped reason appears; primary endpoint(s) rewritten.
- notable: any other status change, phase change, new trial, lead-sponsor change, results posted, arm or intervention
  change, enrollment change of 20% or more, start / primary completion / completion date moved 30+ days.
- minor: everything else (small date or enrollment tweaks, site-count changes, title edits).
"""
from __future__ import annotations
from datetime import date

LEVELS = ("minor", "notable", "critical")
STOPPED = {"TERMINATED", "SUSPENDED", "WITHDRAWN"}
DATE_FIELDS = {"start_date", "primary_completion_date", "completion_date"}
NOTABLE_FIELDS = {"phase", "lead_sponsor", "arm_count", "interventions", "has_results", "results_first_posted"}


def _date(v) -> date | None:
    """CT.gov dates are YYYY-MM-DD or YYYY-MM (month precision -> 1st of the month)."""
    s = str(v or "").strip()
    try:
        if len(s) == 7: return date(int(s[:4]), int(s[5:7]), 1)
        if len(s) == 10: return date.fromisoformat(s)
    except ValueError:
        return None
    return None


def shift_days(old, new) -> int | None:
    a, b = _date(old), _date(new)
    return (b - a).days if a and b else None


def _num(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def severity(c: dict) -> str:
    kind, f, old, new = c.get("kind"), c.get("field"), c.get("old"), c.get("new")
    if kind == "new_trial": return "notable"
    if f == "status": return "critical" if str(new or "").upper() in STOPPED else "notable"
    if f == "why_stopped": return "critical" if new not in (None, "", "None") else "minor"
    if f == "primary_outcomes": return "critical"
    if f in NOTABLE_FIELDS: return "notable"
    if f == "enrollment":
        o, n = _num(old), _num(new)
        if o and n is not None and abs(n - o) / o >= 0.2: return "notable"
        return "minor" if o else "notable"
    if f in DATE_FIELDS:
        d = shift_days(old, new)
        return "notable" if d is None or abs(d) >= 30 else "minor"
    return "minor"


def annotate(changes: list[dict]) -> list[dict]:
    for c in changes:
        c["severity"] = severity(c)
        if c.get("field") in DATE_FIELDS: c["shift_days"] = shift_days(c.get("old"), c.get("new"))
    return changes


def at_least(changes: list[dict], level: str | None) -> list[dict]:
    if not level: return changes
    if level not in LEVELS: raise ValueError(f"severity must be one of {', '.join(LEVELS)}")
    lo = LEVELS.index(level)
    return [c for c in changes if LEVELS.index(c.get("severity") or severity(c)) >= lo]
