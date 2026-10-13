"""Flatten openFDA records into stable, diffable rows."""
from __future__ import annotations

SUB_TRACKED = ["submission_status", "submission_status_date", "review_priority", "submission_class",
               "n_docs", "brand_names", "sponsor"]
LABEL_TRACKED = ["version", "effective_time", "brand_name"]
STATUS = {"AP": "APPROVED", "TA": "TENTATIVE_APPROVAL"}


def iso(d: str | None) -> str | None:
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if d and len(d) >= 8 and d.isdigit() else d


def application_url(appno: str) -> str:
    num = "".join(c for c in appno if c.isdigit())
    return f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={num}"


def submissions(app: dict) -> list[dict]:
    """One row per submission (ORIG approvals, supplements: efficacy, labeling, CMC, ...)."""
    appno = app.get("application_number")
    prods = app.get("products", []) or []
    brands = sorted({p.get("brand_name") for p in prods if p.get("brand_name")})
    ingr = sorted({i.get("name") for p in prods for i in (p.get("active_ingredients") or []) if i.get("name")})
    of = app.get("openfda", {}) or {}
    rows = []
    for s in app.get("submissions", []) or []:
        docs = s.get("application_docs", []) or []
        latest = max(docs, key=lambda d: d.get("date") or "", default={})
        label = next((d.get("url") for d in sorted(docs, key=lambda d: d.get("date") or "", reverse=True) if d.get("type") == "Label"), None)
        rows.append({
            "key": f"{appno}:{s.get('submission_type')}{s.get('submission_number')}",
            "application_number": appno,
            "sponsor": app.get("sponsor_name"),
            "brand_names": "; ".join(brands) or None,
            "active_ingredients": "; ".join(ingr) or None,
            "submission_type": s.get("submission_type"),
            "submission_number": s.get("submission_number"),
            "submission_status": STATUS.get(s.get("submission_status"), s.get("submission_status")),
            "submission_status_date": iso(s.get("submission_status_date")),
            "review_priority": s.get("review_priority"),
            "submission_class": s.get("submission_class_code_description") or s.get("submission_class_code"),
            "n_docs": len(docs),
            "latest_doc_date": iso(latest.get("date")),
            "label_url": label,
            "pharm_class": "; ".join((of.get("pharm_class_epc") or [])[:2]) or None,
            "url": application_url(appno or ""),
        })
    return rows


def is_novel(row: dict) -> bool:
    """Original approval of an NME (NDA Type 1) or an original BLA."""
    if row.get("submission_type") != "ORIG" or row.get("submission_status") != "APPROVED":
        return False
    cls = row.get("submission_class") or ""
    if "New Molecular Entity" in cls: return True
    # BLAs: approximate (openFDA lacks CDER/CBER novelty flag); exclude new formulation/manufacturer (biosimilar-like) and ORIG2+
    return (row.get("application_number") or "").startswith("BLA") and row.get("submission_number") == "1" and not cls.startswith("Type 5")


def label(rec: dict) -> dict:
    of = rec.get("openfda", {}) or {}
    first = lambda k: (of.get(k) or [None])[0]
    return {
        "key": rec.get("set_id"),
        "set_id": rec.get("set_id"),
        "version": rec.get("version"),
        "effective_time": iso(rec.get("effective_time")),
        "brand_name": first("brand_name"),
        "generic_name": first("generic_name"),
        "manufacturer": first("manufacturer_name"),
        "application_number": first("application_number"),
        "url": f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={rec.get('set_id')}",
    }
