from __future__ import annotations
import csv
from collections import Counter

COLS = ["nct_id", "title", "lead_sponsor", "phase", "status", "enrollment", "start_date",
        "primary_completion_date", "last_update_posted", "conditions", "interventions", "url"]


def write_csv(path, rows, cols=None):
    cols = cols or (COLS if rows and "nct_id" in rows[0] and "kind" not in rows[0] else list(rows[0].keys()) if rows else COLS)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def sponsor_pipeline(records: list[dict]) -> dict:
    active = {"RECRUITING", "NOT_YET_RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"}
    return {
        "total": len(records),
        "by_phase": dict(Counter(r.get("phase") or "N/A" for r in records).most_common()),
        "by_status": dict(Counter(r.get("status") for r in records).most_common()),
        "active": sorted([{k: r.get(k) for k in ("nct_id", "phase", "status", "title", "primary_completion_date")}
                          for r in records if r.get("status") in active],
                         key=lambda x: (x["primary_completion_date"] or "9999")),
    }


def markdown(title: str, records: list[dict], changes: list[dict], note: str = "") -> str:
    L = [f"# {title}", "", note, ""]
    if changes:
        L += ["## What changed", "", "| Severity | NCT | Sponsor | Change | Field | Old → New |", "|---|---|---|---|---|---|"]
        order = {"critical": 0, "notable": 1, "minor": 2}
        for c in sorted(changes, key=lambda c: order.get(c.get("severity"), 3)):
            sd = f" ({c['shift_days']:+d} d)" if c.get("shift_days") is not None else ""
            cell = lambda v: str(v or "").replace("|", "/")[:200]
            L.append(f"| {c.get('severity') or ''} | [{c['nct_id']}](https://clinicaltrials.gov/study/{c['nct_id']}) | {c.get('sponsor') or ''} | {c['kind']} | {c['field'] or ''} | {cell(c['old'])} → {cell(c['new'])}{sd} |")
        L.append("")
    else:
        L += ["## What changed", "", "_No changes vs previous snapshot (or this is the baseline run)._", ""]
    pipe = sponsor_pipeline(records)
    L += ["## Snapshot summary", "", f"Trials: **{pipe['total']}**", "",
          "By phase: " + ", ".join(f"{k}: {v}" for k, v in pipe["by_phase"].items()), "",
          "By status: " + ", ".join(f"{k}: {v}" for k, v in pipe["by_status"].items()), "",
          "## Trials (most recently updated first)", "",
          "| NCT | Sponsor | Phase | Status | N | Primary completion | Updated | Title |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(records, key=lambda r: r.get("last_update_posted") or "", reverse=True):
        L.append(f"| [{r['nct_id']}]({r['url']}) | {r['lead_sponsor']} | {r['phase'] or ''} | {r['status']} | {r['enrollment'] or ''} | {r['primary_completion_date'] or ''} | {r['last_update_posted']} | {(r['title'] or '')[:90]} |")
    L += ["", "_Source: ClinicalTrials.gov API v2 (U.S. National Library of Medicine). Data is public; see clinicaltrials.gov/about-site/terms-conditions._"]
    return "\n".join(L)
