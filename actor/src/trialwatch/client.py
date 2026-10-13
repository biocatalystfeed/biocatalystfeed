"""Minimal ClinicalTrials.gov API v2 client (public, no key). No official numeric rate limit is published; ~50 req/min/IP is
reported by third parties, so we throttle to <=46/min and back off on 429/5xx."""
from __future__ import annotations
import time
import requests

BASE = "https://clinicaltrials.gov/api/v2"
UA = "BioCatalystFeed-trialwatch/0.2"
FIELDS = ",".join([
    "NCTId", "BriefTitle", "Acronym", "OverallStatus", "Phase", "StudyType",
    "LeadSponsorName", "LeadSponsorClass", "CollaboratorName", "Condition",
    "InterventionName", "InterventionType", "EnrollmentCount", "EnrollmentType",
    "StartDate", "PrimaryCompletionDate", "CompletionDate", "StudyFirstPostDate",
    "LastUpdatePostDate", "WhyStopped", "HasResults",
])
PHASES = {"EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"}
STATUSES = {"NOT_YET_RECRUITING", "RECRUITING", "ENROLLING_BY_INVITATION",
            "ACTIVE_NOT_RECRUITING", "SUSPENDED", "TERMINATED", "COMPLETED",
            "WITHDRAWN", "UNKNOWN", "AVAILABLE", "NO_LONGER_AVAILABLE",
            "TEMPORARILY_NOT_AVAILABLE", "APPROVED_FOR_MARKETING", "WITHHELD"}


class CTGovClient:
    def __init__(self, min_interval: float = 1.3, session: requests.Session | None = None):
        self.min_interval = min_interval
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = UA
        self._last = 0.0

    def _get(self, path: str, params: dict) -> dict:
        for attempt in range(4):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            r = self.s.get(BASE + path, params=params, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return {}

    @staticmethod
    def build_params(sponsor=None, condition=None, intervention=None, term=None,
                     phases=None, statuses=None, changed_since=None) -> dict:
        p: dict = {"fields": FIELDS, "format": "json"}
        if sponsor: p["query.spons"] = sponsor
        if condition: p["query.cond"] = condition
        if intervention: p["query.intr"] = intervention
        if term: p["query.term"] = term
        if statuses:
            bad = set(s.upper() for s in statuses) - STATUSES
            if bad: raise ValueError(f"unknown status {bad}")
            p["filter.overallStatus"] = ",".join(s.upper() for s in statuses)
        adv = []
        if phases:
            bad = set(x.upper() for x in phases) - PHASES
            if bad: raise ValueError(f"unknown phase {bad}")
            adv.append("(" + " OR ".join(f"AREA[Phase]{x.upper()}" for x in phases) + ")")
        if changed_since:
            adv.append(f"AREA[LastUpdatePostDate]RANGE[{changed_since},MAX]")
        if adv:
            p["filter.advanced"] = " AND ".join(adv)
        return p

    def search(self, max_records: int = 500, **kw) -> list[dict]:
        params = self.build_params(**kw)
        params["pageSize"] = min(1000, max_records)
        out: list[dict] = []
        while True:
            data = self._get("/studies", params)
            out.extend(data.get("studies", []))
            tok = data.get("nextPageToken")
            if not tok or len(out) >= max_records:
                return out[:max_records]
            params["pageToken"] = tok

    def get(self, nct_id: str) -> dict:
        return self._get(f"/studies/{nct_id.upper()}", {"fields": FIELDS})
