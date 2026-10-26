"""Opt-in "Global" coverage (Phase 1): labels and link-outs only.

Phase 1 adds two things, both off by default:
- Trials: link-outs to records in non-FDA/EMA registries, found in ClinicalTrials.gov secondary IDs. We store and
  show only the registry ID and a link; we do not fetch, scrape or ingest the foreign registry record. WHO ICTRP data,
  ChiCTR pages and the NMPA/CDE platform are NOT ingested (licence/terms not cleared).
- Papers: a jurisdiction_flag from author-affiliation countries (Europe PMC metadata). Unknown country -> "unknown";
  the pipeline never guesses.
Factual labelling only: no ranking or grading of foreign data, and no medical, legal or investment advice.
"""
from __future__ import annotations
import re

REGISTRY_CLASS = "non-FDA/EMA registry"
PAPER_FLAG = "non-FDA/EMA oversight"
LABEL = "non-FDA/EMA"
GLOBAL_DISCLAIMER = (
    'Results labelled "non-FDA/EMA registry" come from registries and studies that may operate under regulatory, '
    "ethics and data standards different from, and sometimes lighter than, those of the US FDA or the EU's EMA. "
    "They are included because you opted in to see everything that is out there. Inclusion is not an endorsement or "
    "recommendation and is not medical, legal or investment advice.")
TIP = ("tip: add --global to include non-FDA/EMA registries (e.g. China's ChiCTR, NMPA); results are labelled. "
       "Details: bcf --global --help")
HEADER = "Global ON · non-FDA/EMA registries included · not advice · bcf --global --help"
HELP = """--global   Opt-in. Also search non-FDA/EMA trial registries (ChiCTR, NMPA/CDE
           platform, other WHO ICTRP registries) and flag papers from other
           jurisdictions. Off by default.
           Records may come from research run under regulatory, ethics and data
           standards different from, and sometimes lighter than, US FDA or EU
           EMA standards; registry records can be less complete or less current.
           Every such record is labelled "non-FDA/EMA registry" with source and
           country, and JSON output adds registry_class and global_disclaimer.
           Inclusion is not an endorsement or recommendation and is not medical,
           legal or investment advice.
--global-sources LIST   limit to e.g. chictr,nmpa,ictrp

Phase 1 status (what --global does today):
  trials: link-outs only. Registry IDs found in ClinicalTrials.gov secondary
          IDs (e.g. ChiCTR, CTRI, jRCT, ISRCTN) are listed with a link; the
          foreign record itself is not fetched or stored. Direct ChiCTR,
          NMPA/CDE and WHO ICTRP data feeds are not enabled yet (terms/licence
          not cleared), so 'nmpa' currently matches nothing.
  papers: each paper gets jurisdiction_flag "non-FDA/EMA oversight" when an
          author-affiliation country is outside the US/EU/EEA, "unknown" when
          no country is found (never guessed).
"""

ICTRP = "https://trialsearch.who.int/Trial2.aspx?TrialID={}"
# (registry, source key, jurisdiction, regex, url template). Link-outs only.
REGISTRIES = [
    ("ChiCTR", "chictr", "China", r"ChiCTR[-A-Z]*\d{6,}", ICTRP),
    ("WHO-ICTRP:CTRI", "ictrp", "India", r"CTRI/\d{4}/\d{2,3}/\d{6}", ICTRP),
    ("WHO-ICTRP:jRCT", "ictrp", "Japan", r"jRCT[a-z]?\d{7,10}", ICTRP),
    ("WHO-ICTRP:JPRN", "ictrp", "Japan", r"JPRN-[A-Za-z]+-?\d+", ICTRP),
    ("WHO-ICTRP:CRIS", "ictrp", "South Korea", r"KCT\d{7}", ICTRP),
    ("WHO-ICTRP:ANZCTR", "ictrp", "Australia/New Zealand", r"ACTRN\d{14}", ICTRP),
    ("WHO-ICTRP:ReBEC", "ictrp", "Brazil", r"RBR-[0-9a-z]{6,8}", ICTRP),
    ("WHO-ICTRP:PACTR", "ictrp", "Africa", r"PACTR\d{15,16}", ICTRP),
    ("WHO-ICTRP:IRCT", "ictrp", "Iran", r"IRCT\d{8,}N\d+", ICTRP),
    ("WHO-ICTRP:TCTR", "ictrp", "Thailand", r"TCTR\d{11}", ICTRP),
    ("WHO-ICTRP:ISRCTN", "ictrp", "United Kingdom/international", r"ISRCTN\d{8}", "https://www.isrctn.com/{}"),
]
SOURCES = ("chictr", "nmpa", "ictrp")


def parse_sources(v) -> set[str] | None:
    if not v: return None
    items = [x.strip().lower() for x in (v.split(",") if isinstance(v, str) else v) if x and x.strip()]
    bad = set(items) - set(SOURCES)
    if bad: raise ValueError(f"unknown global source(s) {sorted(bad)}; choose from {', '.join(SOURCES)}")
    return set(items)


def registry_links(secondary_ids, nct_id: str | None = None, sources: set[str] | None = None) -> list[dict]:
    """secondary_ids: strings or ClinicalTrials.gov secondaryIdInfos dicts. Returns labelled link-out records."""
    out, seen = [], set()
    for s in secondary_ids or []:
        sid = (s.get("id") if isinstance(s, dict) else s) or ""
        for reg, key, juris, rx, url in REGISTRIES:
            if sources and key not in sources: continue
            m = re.search(rx, sid)
            if m and m.group(0) not in seen:
                rid = m.group(0); seen.add(rid)
                out.append({"registry_class": REGISTRY_CLASS, "registry": reg, "registry_id": rid, "jurisdiction": juris,
                            "source_url": url.format(rid), "also_registered_as": nct_id, "link_only": True})
    return out


def secondary_ids(study: dict) -> list:
    return ((study.get("protocolSection") or {}).get("identificationModule") or {}).get("secondaryIdInfos") or []


# --- papers: affiliation countries -------------------------------------------------------------------------------
US_EU_EEA = ["United States", "USA", "U.S.A.", "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic",
             "Czechia", "Denmark", "Estonia", "Finland", "France", "Germany", "Greece", "Hungary", "Ireland", "Italy",
             "Latvia", "Lithuania", "Luxembourg", "Malta", "Netherlands", "The Netherlands", "Poland", "Portugal",
             "Romania", "Slovakia", "Slovenia", "Spain", "Sweden", "Iceland", "Liechtenstein", "Norway"]
OTHER = ["China", "P.R. China", "PR China", "Hong Kong", "Macau", "Taiwan", "Japan", "Korea", "Republic of Korea", "India",
         "Iran", "Brazil", "United Kingdom", "UK", "England", "Scotland", "Wales", "Northern Ireland", "Switzerland",
         "Canada", "Australia", "New Zealand", "Russia", "Russian Federation", "Turkey", "Türkiye", "Israel", "Egypt",
         "Saudi Arabia", "Pakistan", "Singapore", "Mexico", "South Africa", "Nigeria", "Thailand", "Vietnam", "Viet Nam",
         "Malaysia", "Indonesia", "Argentina", "Chile", "Colombia", "Peru", "Bangladesh", "Philippines", "Ukraine",
         "Serbia", "Qatar", "United Arab Emirates", "UAE", "Jordan", "Lebanon", "Ethiopia", "Kenya", "Ghana", "Uganda",
         "Tanzania", "Morocco", "Tunisia", "Nepal", "Sri Lanka", "Kazakhstan", "Belarus"]
CANON = {"USA": "United States", "U.S.A.": "United States", "Czechia": "Czech Republic", "The Netherlands": "Netherlands",
         "P.R. China": "China", "PR China": "China", "Republic of Korea": "South Korea", "Korea": "South Korea",
         "UK": "United Kingdom", "England": "United Kingdom", "Scotland": "United Kingdom", "Wales": "United Kingdom",
         "Northern Ireland": "United Kingdom", "Russian Federation": "Russia", "Türkiye": "Turkey", "Viet Nam": "Vietnam",
         "UAE": "United Arab Emirates"}
_HOME = {CANON.get(c, c) for c in US_EU_EEA}
_ALL = sorted(set(US_EU_EEA + OTHER), key=len, reverse=True)
_RX = re.compile(r"(?<![A-Za-z])(?<!New )(?<!New South )(" + "|".join(re.escape(c) for c in _ALL) + r")(?![A-Za-z])")


def countries(affiliations) -> list[str]:
    found = []
    for a in affiliations or []:
        a = re.sub(r"\S+@\S+", " ", str(a))  # drop emails
        for m in _RX.finditer(a):
            c = CANON.get(m.group(1), m.group(1))
            if c == "Ireland" and "Northern Ireland" in a: continue
            if c not in found: found.append(c)
    return found


def paper_flag(affiliations) -> tuple[str | None, list[str]]:
    cs = countries(affiliations)
    if not cs: return "unknown", []
    return (PAPER_FLAG if any(c not in _HOME for c in cs) else None), cs


def epmc_affiliations(r: dict) -> list[str]:
    out = []
    for au in ((r.get("authorList") or {}).get("author") or []):
        for d in ((au.get("authorAffiliationDetailsList") or {}).get("authorAffiliation") or []):
            if d.get("affiliation"): out.append(d["affiliation"])
        if au.get("affiliation"): out.append(au["affiliation"])
    if not out and r.get("affiliation"): out.append(r["affiliation"])
    return out


def lookup_affiliations(epmc, papers: list[dict], batch: int = 25) -> dict:
    """Europe PMC core metadata by PMID/DOI -> {paper key: [affiliations]}. Metadata only."""
    want = {}
    for p in papers:
        pmid = p.get("pmid") or (p.get("id") if p.get("source") == "pubmed" else None)
        if pmid: want[f"EXT_ID:{pmid} AND SRC:MED"] = p["key"]
        elif p.get("doi"): want[f'DOI:"{p["doi"]}"'] = p["key"]
    out, items = {}, list(want.items())
    for i in range(0, len(items), batch):
        chunk = items[i:i + batch]
        _, res = epmc.search(" OR ".join(f"({q})" for q, _ in chunk), max_records=len(chunk) * 2)
        for r in res:
            affs = epmc_affiliations(r)
            for k in (f"EXT_ID:{r.get('pmid')} AND SRC:MED" if r.get("pmid") else None,
                      f'DOI:"{r.get("doi")}"' if r.get("doi") else None):
                if k and k in want: out.setdefault(want[k], affs)
            if r.get("doi"):
                for q, key in chunk:
                    if q.lower() == f'doi:"{r["doi"]}"'.lower(): out.setdefault(key, affs)
    return out


def annotate_papers(papers: list[dict], affs_by_key: dict) -> list[dict]:
    for p in papers:
        flag, cs = paper_flag(affs_by_key.get(p["key"]))
        p["jurisdiction_flag"] = flag
        p["jurisdiction"] = cs
        if flag == PAPER_FLAG: p["registry_class"] = REGISTRY_CLASS
    return papers


def text_label(rec: dict) -> str:
    if rec.get("registry_id"):
        return f"[{REGISTRY_CLASS}] {rec['registry']} ({rec['jurisdiction']})"
    if rec.get("jurisdiction_flag") == PAPER_FLAG:
        return f"[{PAPER_FLAG}] ({', '.join(c for c in rec['jurisdiction'] if c not in _HOME)})"
    if rec.get("jurisdiction_flag") == "unknown":
        return "[jurisdiction unknown]"
    return ""


def is_global(rec: dict) -> bool:
    return bool(rec.get("registry_id") or rec.get("jurisdiction_flag") == PAPER_FLAG or rec.get("global_links"))
