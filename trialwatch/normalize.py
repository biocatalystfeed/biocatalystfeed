"""Flatten a CT.gov v2 study into a stable, diffable record."""
from __future__ import annotations

TRACKED = ["status", "phase", "enrollment", "start_date", "primary_completion_date",
           "completion_date", "lead_sponsor", "title", "why_stopped", "has_results"]


def _d(struct):
    return (struct or {}).get("date")


def normalize(study: dict) -> dict:
    ps = study.get("protocolSection", {})
    idm, st = ps.get("identificationModule", {}), ps.get("statusModule", {})
    sp, de = ps.get("sponsorCollaboratorsModule", {}), ps.get("designModule", {})
    cond = ps.get("conditionsModule", {})
    arms = ps.get("armsInterventionsModule", {})
    enr = de.get("enrollmentInfo", {}) or {}
    return {
        "nct_id": idm.get("nctId"),
        "title": idm.get("briefTitle"),
        "acronym": idm.get("acronym"),
        "status": st.get("overallStatus"),
        "why_stopped": st.get("whyStopped"),
        "phase": "/".join(de.get("phases", []) or []) or None,
        "study_type": de.get("studyType"),
        "lead_sponsor": (sp.get("leadSponsor") or {}).get("name"),
        "sponsor_class": (sp.get("leadSponsor") or {}).get("class"),
        "collaborators": "; ".join(c.get("name", "") for c in sp.get("collaborators", []) or []) or None,
        "conditions": "; ".join(cond.get("conditions", []) or []) or None,
        "interventions": "; ".join(f"{i.get('type','')}:{i.get('name','')}" for i in arms.get("interventions", []) or []) or None,
        "enrollment": enr.get("count"),
        "enrollment_type": enr.get("type"),
        "start_date": _d(st.get("startDateStruct")),
        "primary_completion_date": _d(st.get("primaryCompletionDateStruct")),
        "completion_date": _d(st.get("completionDateStruct")),
        "first_posted": _d(st.get("studyFirstPostDateStruct")),
        "last_update_posted": _d(st.get("lastUpdatePostDateStruct")),
        "has_results": bool(study.get("hasResults", False)),
        "url": f"https://clinicaltrials.gov/study/{idm.get('nctId')}",
    }
