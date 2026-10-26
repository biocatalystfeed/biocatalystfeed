"""FDA complete response letters (CRLs) from openFDA (https://api.fda.gov/transparency/crl.json).

Source: U.S. Food and Drug Administration via openFDA. Documented public JSON API, no key required (an optional
OPENFDA_API_KEY raises rate limits). openFDA data is public domain / CC0 (https://open.fda.gov/license/). FDA publishes
CRLs for approved and unapproved NDAs and BLAs, redacted for confidential commercial information. A CRL is a catalyst
signal: FDA has decided it cannot approve the application in its present form and says why (facility inspection,
product quality / CMC, clinical, safety ...). `application_status` says whether the application has since been
approved ("Approved") or not ("Unapproved"); a flip from Unapproved to Approved is reported by `watch`.

Personal fields in the source (company representative, signatory, address) are not copied into BCF records.
"""
from __future__ import annotations
import re
from datetime import date
from biowatch import filters
from biowatch.store import ItemStore
from fdawatch.client import OpenFDAClient, date_range, quote

PATH = "/transparency/crl.json"
PDF_BASE = "https://download.open.fda.gov/crl/"
SOURCE = "U.S. Food and Drug Administration, openFDA complete response letters (open.fda.gov); public domain"
TRACKED = ("application_status", "letter_type")
STATUSES = ("Approved", "Unapproved")
# Deficiency topics from the letter's section headings (boilerplate sections such as PRESCRIBING INFORMATION,
# PROPRIETARY NAME and SAFETY UPDATE are ignored). Order matters: the first matching rule wins for a heading.
TOPIC_RULES = (
    ("human_factors", ("HUMAN FACTORS",)),
    ("clinical_pharmacology", ("CLINICAL PHARMACOLOGY", "BIOPHARMACEUTIC", "BIOEQUIVALENCE")),
    ("nonclinical", ("NONCLINICAL", "TOXICOLOGY", "PHARMACOLOGY/TOXICOLOGY")),
    ("facility", ("FACILITY", "FACILITIES", "INSPECTION")),
    ("product_quality", ("PRODUCT QUALITY", "CHEMISTRY", "MANUFACTURING", "CMC", "MICROBIOLOGY", "DRUG PRODUCT",
                         "DRUG SUBSTANCE", "DEVICE", "COMBINATION PRODUCT", "PROCESS")),
    ("clinical", ("CLINICAL", "STATISTIC", "BIOSTATISTIC", "EFFICACY")),
    ("safety", ("RISK EVALUATION AND MITIGATION", "SAFETY")),
)
TOPICS = tuple(t for t, _ in TOPIC_RULES)
BOILERPLATE = ("SAFETY UPDATE", "PRESCRIBING INFORMATION", "CARTON AND CONTAINER", "PROPRIETARY NAME", "MEDICATION GUIDE",
               "ADDITIONAL COMMENT", "OTHER", "LABELING", "COMPLETE RESPONSE", "ADMINISTRATION", "REQUIRED PEDIATRIC",
               "POSTMARKETING", "SUBMISSION OF REMS", "PDUFA", "RECOMMENDATION", "RECOM MENDATION", "PATH FORWARD",
               "TENTATIVE APPROVAL", "REGULATORY", "CENTER FOR DEVICES")
HEADING = re.compile(r"^[ \t]*([A-Z][A-Z ,/&()\-]{3,70})[ \t]*$", re.M)
PRODUCT_RE = re.compile(r"(?:application|supplement)[^.]{0,250}?\bfor\s+([^.;]{3,120}?)\s*(?:\.|;|,\s+(?:and|which|to)\b)", re.S | re.I)
APP_RE = re.compile(r"^(?:(NDA|BLA|BL)\s*)?(\d{6})$", re.I)


def iso(d: str | None) -> str | None:
    """openFDA CRL dates are MM/DD/YYYY."""
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", (d or "").strip())
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else (d or None)


def _topic(heading: str) -> str | None:
    h = re.sub(r"\s+", " ", heading).strip()
    if any(h == b or h.startswith(b) for b in BOILERPLATE): return None
    for topic, needles in TOPIC_RULES:
        if any(n in h for n in needles):
            if topic == "safety" and "SAFETY UPDATE" in h: return None
            return topic
    return None


def sections(text: str) -> list[tuple[str, str, int]]:
    """(heading, topic, offset) for each deficiency heading the topic rules recognise, in letter order."""
    out = []
    for m in HEADING.finditer(text or ""):
        t = _topic(m.group(1))
        if t: out.append((re.sub(r"\s+", " ", m.group(1)).strip(), t, m.end()))
    return out


def topics_of(text: str) -> list[str]:
    seen = []
    for _, t, _ in sections(text):
        if t not in seen: seen.append(t)
    return seen


def excerpt_of(text: str, n: int = 600) -> str | None:
    """Start of the first deficiency section (whitespace collapsed), so a reader sees FDA's main reason."""
    s = sections(text)
    if not s: return None
    body = text[s[0][2]:]
    nxt = HEADING.search(body)
    body = body[:nxt.start()] if nxt and nxt.start() > 80 else body
    body = re.sub(r"\s+", " ", re.sub(r"Reference ID: \d+|(?:NDA|BLA) \d{6}\s+Page \d+", " ", body)).strip()
    return (body[:n].rsplit(" ", 1)[0] + " ...") if len(body) > n else (body or None)


def product_of(text: str) -> str | None:
    """Best-effort product name from the opening 'application ... for <product>.' sentence (OCR text, may be redacted)."""
    m = PRODUCT_RE.search((text or "")[:2500])
    if not m: return None
    v = re.sub(r"\s+", " ", m.group(1)).strip(" ,:")
    v = re.split(r"\s+(?:We|You|This|The)\s", re.sub(r"\(?b\)\s*\(4\)?", "", v))[0].strip(" ,:")
    v = re.sub(r",?\s*for (?:intravenous|oral|subcutaneous|intramuscular|topical|ophthalmic) use$", "", v, flags=re.I)
    if re.match(r"(?:NDA|BLA|BL)\s*\d", v) or not re.search(r"[A-Za-z]{3}", v): return None
    return v


def normalize(r: dict, include_text: bool = False) -> dict:
    text = r.get("text") or ""
    apps = [re.sub(r"\s+", " ", a).strip() for a in (r.get("application_number") or [])]
    d = iso(r.get("letter_date"))
    product = product_of(text)
    company = (r.get("company_name") or "").strip() or None
    fn = r.get("file_name")
    out = {"key": fn or f"{'/'.join(apps)}:{d}", "letter_date": d, "letter_type": r.get("letter_type"),
           "company": company, "applications": ", ".join(apps) or None,
           "application_type": "/".join(sorted({"BLA" if a.split()[0].upper() == "BL" else a.split()[0].upper()
                                                for a in apps if a.split()})) or None,
           "product": product, "application_status": r.get("approval_status"),
           "topics": topics_of(text), "excerpt": excerpt_of(text),
           "title": " ".join(x for x in ("CRL", d, company, ", ".join(apps), f"({product})" if product else "") if x),
           "url": PDF_BASE + fn if fn else None, "date": d, "source": SOURCE}
    if include_text: out["text"] = text
    return out


def build_search(since=None, until=None, company=None, application=None, status=None) -> str:
    parts = [f"letter_date:{date_range(since, until)}"]
    if company:
        cs = [company] if isinstance(company, str) else list(company)
        parts.append("(" + "+OR+".join(f"company_name:{quote(c).replace(' ', '+')}" for c in cs) + ")")
    if application:
        m = APP_RE.match(application.strip())
        if not m: raise ValueError("application must look like 'NDA 218705', 'BLA 761308' or '218705'")
        parts.append(f"application_number:*{m.group(2)}*")  # exact-keyword field: values like 'BL 125827', 'BLA 761303/Original 1'
    if status:
        ss = [status] if isinstance(status, str) else list(status)
        bad = [s for s in ss if s not in STATUSES]
        if bad: raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        parts.append("(" + "+OR+".join(f"approval_status:{s}" for s in ss) + ")")
    return "+AND+".join(parts)


def letters(client: OpenFDAClient, since: str | None = None, until: str | None = None, company=None,
            application: str | None = None, status=None, keyword: str | None = None, topic=None, exclude=None,
            rank: bool = False, include_text: bool = False, max_records: int = 50, scan: int = 1000) -> list[dict]:
    """CRLs newest letter first. company / application / status / date window are filtered by openFDA; keyword
    (drug, product or any word in the letter) and topic (facility, product_quality, clinical, safety, ...) are
    filtered locally over up to `scan` letters."""
    topics = [topic] if isinstance(topic, str) else list(topic or [])
    bad = [t for t in topics if t not in TOPICS]
    if bad: raise ValueError(f"topic must be among {', '.join(TOPICS)}")
    local = bool(keyword or topics or exclude)
    raw = client.query(PATH, build_search(since, until, company, application, status),
                       max_records=max(scan, max_records) if local else max_records, sort="letter_date:desc")
    out = []
    for r in raw:
        n = normalize(r, include_text=True)
        if keyword and not filters._hit(" ".join(str(x or "") for x in (n["company"], n["product"], n["applications"], n["text"])).lower(), keyword):
            continue
        if topics and not set(topics) & set(n["topics"]): continue
        if not include_text: n.pop("text", None)
        out.append(n)
    out = filters.exclude(out, exclude, fields=("title", "company", "product", "excerpt"))
    if rank: out = filters.rank(out, keyword, *(company if isinstance(company, list) else [company]))
    return out[:max_records]


def store(path: str) -> ItemStore:
    return ItemStore(path, "crl", TRACKED, new_kind="new_letter")


def run_watch(client: OpenFDAClient, st: ItemStore, watch: str, **kw) -> dict:
    kw.setdefault("max_records", 1000)
    rows = letters(client, **kw)
    for r in rows: r.pop("relevance", None)
    info = st.ingest(watch, rows, query=kw)
    info["changes_detail"] = st.changes(watch=watch, run_id=info["run_id"])
    return info


def today() -> str:
    return date.today().isoformat()
