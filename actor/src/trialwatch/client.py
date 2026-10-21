"""Minimal ClinicalTrials.gov API v2 client (public, no key). No official numeric rate limit is published; ~50 req/min/IP is
reported by third parties, so we throttle to <=46/min and back off on 429/5xx."""
from __future__ import annotations
import re, time
import requests
from biowatch.http import retry_delay, is_retryable

BASE = "https://clinicaltrials.gov/api/v2"
UA = "BioCatalystFeed-trialwatch/0.3"
FIELDS = ",".join([
    "NCTId", "BriefTitle", "Acronym", "OverallStatus", "Phase", "StudyType",
    "LeadSponsorName", "LeadSponsorClass", "CollaboratorName", "Condition",
    "InterventionName", "InterventionType", "EnrollmentCount", "EnrollmentType",
    "StartDate", "PrimaryCompletionDate", "CompletionDate", "StudyFirstPostDate",
    "LastUpdatePostDate", "WhyStopped", "HasResults", "ResultsFirstPostDate",
    "PrimaryOutcomeMeasure", "ArmGroupLabel", "LocationFacility",
])
PHASES = {"EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"}
STATUSES = {"NOT_YET_RECRUITING", "RECRUITING", "ENROLLING_BY_INVITATION",
            "ACTIVE_NOT_RECRUITING", "SUSPENDED", "TERMINATED", "COMPLETED",
            "WITHDRAWN", "UNKNOWN", "AVAILABLE", "NO_LONGER_AVAILABLE",
            "TEMPORARILY_NOT_AVAILABLE", "APPROVED_FOR_MARKETING", "WITHHELD"}

NCT_RE = re.compile(r"^NCT\d{8}$")


def validate_nct(nct_id: str) -> str:
    v = str(nct_id or "").strip().upper()
    if not NCT_RE.match(v):
        raise ValueError(f"invalid NCT ID {nct_id!r}: expected NCT followed by 8 digits, e.g. NCT04184622")
    return v


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
            try:
                r = self.s.get(BASE + path, params=params, timeout=60)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 3: raise
                time.sleep(retry_delay(attempt, base=3.0)); continue
            if is_retryable(r) and attempt < 3:
                time.sleep(retry_delay(attempt, r, base=3.0))
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
        nct_id = validate_nct(nct_id)
        return self._get(f"/studies/{nct_id.upper()}", {"fields": FIELDS})
