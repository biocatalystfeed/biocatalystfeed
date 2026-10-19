"""EMA medicines data (official daily JSON export of the EMA 'Download medicine data' table).

Source: European Medicines Agency, https://www.ema.europa.eu/en/medicines/download-medicine-data. EMA permits
reproduction and distribution, including commercial use, provided EMA is acknowledged as the source in each copy
(EMA legal notice). Every record therefore carries a `source` attribution field."""
from __future__ import annotations
import re
from biowatch import filters
from biowatch.http import Throttled
from biowatch.store import ItemStore

MEDICINES_URL = "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines_json-report_en.json"
SOURCE = "European Medicines Agency (EMA), ema.europa.eu"
DATE_FIELDS = {  # normalized name -> EMA field
    "opinion_date": "opinion_adopted_date",
    "ec_decision_date": "european_commission_decision_date",
    "authorisation_date": "marketing_authorisation_date",
    "refusal_date": "refusal_of_marketing_authorisation_date",
    "application_withdrawn_date": "withdrawal_of_application_date",
    "withdrawn_or_lapsed_date": "withdrawal_expiry_revocation_lapse_of_marketing_authorisation_date",
    "suspension_date": "suspension_of_marketing_authorisation_date",
    "evaluation_start_date": "start_of_evaluation_date",
    "rolling_review_start_date": "start_of_rolling_review_date",
    "first_published": "first_published_date",
    "last_updated": "last_updated_date",
}
FLAGS = ("orphan_medicine", "prime_priority_medicine", "conditional_approval", "accelerated_assessment", "advanced_therapy",
         "biosimilar", "generic", "exceptional_circumstances", "additional_monitoring")
# Regulatory milestones worth an alert. last_updated / revision churn on minor label edits, so they're kept but not tracked.
TRACKED = ("status", "opinion_status", "latest_procedure", "opinion_date", "ec_decision_date", "authorisation_date",
           "refusal_date", "application_withdrawn_date", "withdrawn_or_lapsed_date", "suspension_date", "conditional_approval")


class EMAClient:
    """Fetches the full medicines export once per client (about 7 MB, refreshed by EMA overnight)."""

    def __init__(self, http: Throttled | None = None, url: str = MEDICINES_URL):
        self.http, self.url, self._rows = http or Throttled(min_interval=1.0), url, None

    def medicines(self) -> list[dict]:
        if self._rows is None:
            d = self.http.get_json(self.url)
            self._rows = d.get("data", []) if isinstance(d, dict) else list(d)
        return self._rows


def iso(d: str | None) -> str | None:
    """EMA dates are DD/MM/YYYY; return YYYY-MM-DD (None for blanks/unparseable)."""
    m = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*", d or "")
    return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}" if m else None


def _yes(v) -> bool:
    return str(v or "").strip().lower() in ("yes", "true", "1")


def normalize(r: dict) -> dict:
    out = {"key": r.get("ema_product_number") or r.get("name_of_medicine"), "product_number": r.get("ema_product_number"),
           "title": r.get("name_of_medicine"), "name": r.get("name_of_medicine"),
           "inn": r.get("international_non_proprietary_name_common_name") or None,
           "active_substance": r.get("active_substance") or None, "category": r.get("category") or None,
           "status": r.get("medicine_status") or None, "opinion_status": r.get("opinion_status") or None,
           "latest_procedure": r.get("latest_procedure_affecting_product_information") or None,
           "holder": r.get("marketing_authorisation_developer_applicant_holder") or None,
           "therapeutic_area": r.get("therapeutic_area_mesh") or None, "atc": r.get("atc_code_human") or None,
           "indication": (r.get("therapeutic_indication") or "").strip()[:2000] or None,
           "revision": r.get("revision_number") or None, "url": r.get("medicine_url") or None, "source": SOURCE}
    for k, f in DATE_FIELDS.items(): out[k] = iso(r.get(f))
    for f in FLAGS: out[f] = _yes(r.get(f))
    out["date"] = latest_event(out)
    return out


def latest_event(n: dict) -> str | None:
    """Most recent regulatory milestone date (not the website's last_updated)."""
    ds = [n.get(k) for k in DATE_FIELDS if k not in ("first_published", "last_updated") and n.get(k)]
    return max(ds) if ds else None


def _any(hay: str | None, needles) -> bool:
    h = (hay or "").lower()
    return any(x.lower() in h for x in needles)


def filter_medicines(rows: list[dict], holder=None, drug=None, keyword=None, status=None, category="Human",
                     since: str | None = None, until: str | None = None, orphan: bool = False, prime: bool = False) -> list[dict]:
    L = lambda x: [x] if isinstance(x, str) else list(x or [])
    holder, drug, status = L(holder), L(drug), [s.lower() for s in L(status)]
    out = []
    for n in rows:
        if category and (n.get("category") or "").lower() != category.lower(): continue
        if holder and not _any(n.get("holder"), holder): continue
        if drug and not any(_any(n.get(f), drug) for f in ("name", "inn", "active_substance")): continue
        if keyword and not filters._hit(" ".join(str(n.get(f) or "") for f in ("name", "inn", "active_substance", "therapeutic_area", "indication")).lower(), keyword): continue
        if status and (n.get("status") or "").lower() not in status: continue
        if orphan and not n.get("orphan_medicine"): continue
        if prime and not n.get("prime_priority_medicine"): continue
        if since and not (n.get("date") and n["date"] >= since): continue
        if until and not (n.get("date") and n["date"] <= until): continue
        out.append(n)
    return out


def search_medicines(client: EMAClient, max_records: int = 200, exclude=None, rank: bool = False, **kw) -> list[dict]:
    rows = filter_medicines([normalize(r) for r in client.medicines()], **kw)
    rows.sort(key=lambda n: (n.get("date") or "", n.get("key") or ""), reverse=True)
    rows = filters.exclude(rows, exclude, fields=("name", "inn", "active_substance", "therapeutic_area", "indication"))
    if rank: rows = filters.rank(rows, kw.get("drug"), kw.get("keyword"), kw.get("holder"))
    return rows[:max_records]


def store(path: str) -> ItemStore:
    return ItemStore(path, "ema", TRACKED, new_kind="new_medicine")


def run_watch(client: EMAClient, st: ItemStore, watch: str, max_records: int = 2000, **kw) -> dict:
    rows = search_medicines(client, max_records=max_records, **kw)
    for r in rows: r.pop("relevance", None)
    info = st.ingest(watch, rows, query=kw)
    info["changes_detail"] = st.changes(watch=watch, run_id=info["run_id"])
    return info
