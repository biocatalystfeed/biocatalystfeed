"""Sponsor alias table: one canonical company -> the names each source actually uses.

ct_queries   : strings sent to ClinicalTrials.gov query.spons (free text)
ct_lead      : case-insensitive substrings a trial's *lead* sponsor must contain to be kept (drops collaborator-only hits)
fda_sponsors : exact Drugs@FDA sponsor_name values (abbreviated upper-case in openFDA, e.g. 'LILLY')
label_mfrs   : openfda.manufacturer_name values on SPL labels
nih_orgs     : exact NIH RePORTER org_name values (grantwatch)
pubmed_affil : PubMed [ad] affiliation phrases; preprint_affil: substrings for bioRxiv/medRxiv corresponding institution
drugs        : key asset names/codes (PubMed [tiab]/[nm], preprint text, RePORTER text search)
sec_cik      : SEC EDGAR CIK (secwatch)
Verified against the live APIs on 2026-10-12 PT. Extend via a JSON file passed as FDAWATCH_ALIASES (same shape)."""
from __future__ import annotations
import json, os, re

ALIASES: dict[str, dict] = {
    "Viking Therapeutics": {"ticker": "VKTX", "ct_queries": ["Viking Therapeutics"], "ct_lead": ["viking therapeutics"],
                            "fda_sponsors": [], "label_mfrs": []},
    "Eli Lilly": {"ticker": "LLY", "ct_queries": ["Eli Lilly and Company"], "ct_lead": ["eli lilly"],
                  "fda_sponsors": ["LILLY", "ELI LILLY AND CO"], "label_mfrs": ["Eli Lilly and Company"],
                  "aka": ["Lilly", "Eli Lilly and Company"]},
    "Madrigal Pharmaceuticals": {"ticker": "MDGL", "ct_queries": ["Madrigal Pharmaceuticals"], "ct_lead": ["madrigal"],
                                 "fda_sponsors": ["MADRIGAL"], "label_mfrs": ["Madrigal Pharmaceuticals, Inc."], "aka": ["Madrigal"]},
    "Terns Pharmaceuticals": {"ticker": "TERN", "ct_queries": ["Terns, Inc.", "Terns Pharmaceuticals"], "ct_lead": ["terns"],
                              "fda_sponsors": [], "label_mfrs": [], "aka": ["Terns", "Terns, Inc."],
                              "note": "CT.gov lead sponsor is 'Terns, Inc., a subsidiary of Merck & Co., Inc. (Rahway, New Jersey USA)'"},
    "Novo Nordisk": {"ticker": "NVO", "ct_queries": ["Novo Nordisk A/S"], "ct_lead": ["novo nordisk"],
                     "fda_sponsors": ["NOVO", "NOVO NORDISK INC"],
                     "label_mfrs": ["Novo Nordisk", "Novo Nordisk Pharma, Inc."], "aka": ["Novo"]},
    "Zealand Pharma": {"ticker": "ZEAL.CO", "ct_queries": ["Zealand Pharma"], "ct_lead": ["zealand"],
                       "fda_sponsors": [], "label_mfrs": []},
    "Structure Therapeutics": {"ticker": "GPCR", "ct_queries": ["Structure Therapeutics"], "ct_lead": ["structure therapeutics"],
                               "fda_sponsors": [], "label_mfrs": []},
    "Altimmune": {"ticker": "ALT", "ct_queries": ["Altimmune"], "ct_lead": ["altimmune"], "fda_sponsors": [], "label_mfrs": []},
}


# grantwatch / paperwatch / secwatch fields (added 2026-10-12 PT; CIKs from sec.gov/files/company_tickers.json,
# RePORTER org_name verified live; Terns has no SEC ticker entry after the Merck acquisition, Zealand is not SEC-registered)
_EXT = {'Viking Therapeutics': {'nih_orgs': [], 'pubmed_affil': ['Viking Therapeutics'], 'drugs': ['VK2735', 'VK2809', 'VK0214'], 'sec_cik': '1607678'}, 'Eli Lilly': {'nih_orgs': ['ELI LILLY AND COMPANY'], 'pubmed_affil': ['Eli Lilly and Company', 'Lilly Research Laboratories'], 'preprint_affil': ['Eli Lilly', 'Lilly Research'], 'drugs': ['tirzepatide', 'orforglipron', 'retatrutide'], 'sec_cik': '59478'}, 'Madrigal Pharmaceuticals': {'nih_orgs': [], 'pubmed_affil': ['Madrigal Pharmaceuticals'], 'preprint_affil': ['Madrigal'], 'drugs': ['resmetirom', 'MGL-3196'], 'sec_cik': '1157601'}, 'Terns Pharmaceuticals': {'nih_orgs': [], 'pubmed_affil': ['Terns Pharmaceuticals', 'Terns, Inc'], 'preprint_affil': ['Terns Pharmaceuticals'], 'drugs': ['TERN-501', 'TERN-601', 'TERN-701'], 'sec_cik': None}, 'Novo Nordisk': {'nih_orgs': [], 'pubmed_affil': ['Novo Nordisk'], 'drugs': ['semaglutide', 'cagrilintide', 'CagriSema'], 'sec_cik': '353278'}, 'Zealand Pharma': {'nih_orgs': [], 'pubmed_affil': ['Zealand Pharma'], 'drugs': ['petrelintide', 'survodutide', 'dapiglutide'], 'sec_cik': None}, 'Structure Therapeutics': {'nih_orgs': [], 'pubmed_affil': ['Structure Therapeutics'], 'drugs': ['aleniglipron', 'GSBR-1290'], 'sec_cik': '1888886'}, 'Altimmune': {'nih_orgs': [], 'pubmed_affil': ['Altimmune'], 'drugs': ['pemvidutide'], 'sec_cik': '1326190'}}
for _k, _v in _EXT.items():
    ALIASES[_k].update(_v)


def _key(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    s = re.sub(r"\b(inc|corp|corporation|co|ltd|plc|a s|ag|sa|llc|company|and)\b", " ", s)
    return " ".join(s.split())


def table() -> dict[str, dict]:
    t = dict(ALIASES)
    p = os.environ.get("FDAWATCH_ALIASES")
    if p and os.path.exists(p):
        t.update(json.load(open(p)))
    return t


def resolve(name: str) -> dict:
    """Return {canonical, ticker, ct_queries, ct_lead, fda_sponsors, label_mfrs, known}. Matches canonical name, ticker,
    aka entries, CT queries, or FDA sponsor names (normalized). Unknown names fall back to the raw string."""
    k = _key(name)
    for canon, a in table().items():
        cands = [canon, a.get("ticker", ""), *a.get("aka", []), *a.get("ct_queries", []), *a.get("fda_sponsors", [])]
        if k and any(_key(c) == k for c in cands if c):
            return {"canonical": canon, "known": True, **a}
    first = name.split()[0] if name.split() else name
    return {"canonical": name, "known": False, "ticker": None, "ct_queries": [name], "ct_lead": [],
            "fda_sponsors": [first.upper()], "label_mfrs": [name], "fda_exact": False,
            "nih_orgs": [], "pubmed_affil": [name], "drugs": [], "sec_cik": None}
