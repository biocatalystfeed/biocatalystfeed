"""Offline tests for grantwatch / paperwatch / secwatch and the merged company_profile."""
import os
from datetime import date
import pytest
from fdawatch.aliases import resolve
from grantwatch import core as g
from paperwatch import core as pw
from secwatch import core as sw

RAW_GRANT = {"appl_id": 111, "project_num": "1R01DK000001-01", "core_project_num": "R01DK000001", "fiscal_year": 2026,
             "project_title": "Resmetirom in MASH", "organization": {"org_name": "ELI LILLY AND COMPANY", "org_state": "IN"},
             "principal_investigators": [{"full_name": "Jane Doe"}], "agency_ic_admin": {"abbreviation": "NIDDK"},
             "award_amount": 500000, "award_notice_date": "2026-09-01T00:00:00", "project_end_date": "2030-08-31T00:00:00",
             "project_detail_url": "https://reporter.nih.gov/project-details/111"}


def test_grant_criteria_and_normalize():
    c = g.build_criteria(org=["ELI LILLY AND COMPANY"], org_exact=True, pi="doe", keyword='"tirzepatide"', since="2026-01-01")
    assert c["org_names_exact_match"] == ["ELI LILLY AND COMPANY"] and c["pi_names"] == [{"any_name": "doe"}]
    assert g.build_criteria(keyword="\"a\" OR \"b\"")["advanced_text_search"] == {"operator": "or", "search_field": "projecttitle,terms,abstracttext", "search_text": "\"a\" \"b\""}
    assert c["award_notice_date"] == {"from_date": "2026-01-01", "to_date": ""} and "tirzepatide" in c["advanced_text_search"]["search_text"]
    with pytest.raises(ValueError): g.build_criteria()
    n = g.normalize(RAW_GRANT)
    assert n["key"] == "111" and n["award_notice_date"] == "2026-09-01" and n["pis"] == "Jane Doe" and n["agency"] == "NIDDK"


def test_grant_store_new_award_and_amount_change(tmp_path):
    st = g.store(str(tmp_path / "b.db"))
    a = g.normalize(RAW_GRANT)
    assert st.ingest("w", [a], now="2026-10-01")["baseline"]
    b = g.normalize(dict(RAW_GRANT, appl_id=222, project_num="5R01DK000001-02", fiscal_year=2027))
    info = st.ingest("w", [dict(a, award_amount=650000), b], now="2026-10-10")
    kinds = {(c["key"], c["kind"]) for c in st.changes(run_id=info["run_id"])}
    assert kinds == {("111", "award_amount_change"), ("222", "new_award")}
    assert not st.changes(since="2026-10-11")


def test_pubmed_term_and_normalize():
    t = pw.pubmed_term(affiliation=["Viking Therapeutics"], drug="VK2735", keyword="obesity")
    assert t == '("Viking Therapeutics"[ad]) AND ("VK2735"[tiab] OR "VK2735"[nm]) AND (obesity)'
    s = {"uid": "123", "title": "T", "authors": [{"name": f"A{i}", "authtype": "Author"} for i in range(8)],
         "fulljournalname": "J", "sortpubdate": "2026/10/01 00:00", "articleids": [{"idtype": "doi", "value": "10.1/x"}], "pubtype": ["Journal Article"]}
    n = pw.norm_pubmed(s)
    assert n["key"] == "pmid:123" and n["doi"] == "10.1/x" and n["date"] == "2026-10-01" and n["authors"].endswith("et al.")
    assert n["url"] == "https://pubmed.ncbi.nlm.nih.gov/123/"


class FakeRx:
    def window(self, server, since, until):
        base = {"authors": "X, A.; Y, B.", "date": "2026-10-05", "category": "pharmacology", "license": "cc_by", "published": "NA"}
        return [dict(base, doi=f"10.1101/{server}.1", title="Resmetirom effects on liver fat", abstract="", version="1",
                     author_corresponding_institution="Univ X"),
                dict(base, doi=f"10.1101/{server}.1", title="Resmetirom effects on liver fat", abstract="", version="2",
                     author_corresponding_institution="Univ X"),
                dict(base, doi=f"10.1101/{server}.2", title="Something else", abstract="no drug", version="1",
                     author_corresponding_institution="Madrigal Pharmaceuticals, Inc."),
                dict(base, doi=f"10.1101/{server}.3", title="antiresmetiromish word", abstract="", version="1",
                     author_corresponding_institution="Z")]


def test_preprint_filter():
    r = pw.search_preprints(FakeRx(), drug=["resmetirom"], until="2026-10-12", servers=("biorxiv",))
    assert [x["key"] for x in r] == ["doi:10.1101/biorxiv.1"] and r[0]["version"] == "2"  # latest version, word-boundary match
    r = pw.search_preprints(FakeRx(), affiliation="Madrigal", until="2026-10-12", servers=("medrxiv",))
    assert r[0]["id"] == "10.1101/medrxiv.2" and r[0]["url"].startswith("https://www.medrxiv.org/content/")


def test_paper_store_new_paper(tmp_path):
    st = pw.store(str(tmp_path / "p.db"))
    a = {"key": "pmid:1", "title": "a", "url": "u1"}
    st.ingest("w", [a], now="2026-10-01")
    info = st.ingest("w", [a, {"key": "pmid:2", "title": "b", "url": "u2"}], now="2026-10-02")
    assert [(c["key"], c["kind"]) for c in st.changes(run_id=info["run_id"])] == [("pmid:2", "new_paper")]


TEXT = ("CONSHOHOCKEN, PA, February 28, 2024 – Madrigal Pharmaceuticals today reported results. "
        "Anticipates resmetirom approval; PDUFA date March 14, 2024 • Reports cash of $634 million. "
        "Specialty Launch of Resmetirom PDUFA: March 14 Full Approval. "
        "The FDA assigned a Prescription Drug User Fee Act (PDUFA) target action date in the first quarter of 2025.")


def test_pdufa_extraction():
    c = sw.extract_candidates(TEXT)
    vals = {x["date_text"]: x for x in c}
    assert "March 14, 2024" in vals and vals["March 14, 2024"]["best"]
    assert "February 28, 2024" not in vals  # dateline is too far from the PDUFA mention
    assert vals["March 14"]["year_inferred"] and sw.infer_year("March 14", "2024-01-08") == "2024-03-14"
    assert sw.infer_year("Jan 5", "2024-06-01") == "2025-01-05"
    assert any("quarter of 2025" in v for v in vals)
    assert sw.doc_url({"_id": "0001193125-24-049116:d743882dex991.htm", "_source": {"ciks": ["0001157601"]}}) == \
        "https://www.sec.gov/Archives/edgar/data/1157601/000119312524049116/d743882dex991.htm"
    assert "@" in sw.UA  # SEC fair-access: declared contact in User-Agent


def test_aliases_extended():
    for name, cik in (("Lilly", "59478"), ("MDGL", "1157601"), ("VKTX", "1607678")):
        a = resolve(name)
        assert a["sec_cik"] == cik and a["drugs"] and a["pubmed_affil"]
    assert resolve("Lilly")["nih_orgs"] == ["ELI LILLY AND COMPANY"]
    assert resolve("Unknown Bio")["drugs"] == []


class FakeGrants:
    def search(self, criteria, max_records=500, sort_field=None):
        return [RAW_GRANT] if "org_names_exact_match" in criteria or "advanced_text_search" in criteria else []


class FakePM:
    def esearch(self, term, mindate=None, maxdate=None, retmax=100): return 1, ["9"]
    def esummary(self, ids): return [{"uid": "9", "title": "Resmetirom paper", "authors": [], "sortpubdate": "2026/09/30", "articleids": []}]


class FakeSEC:
    def submissions(self, cik): return {"name": "MADRIGAL", "tickers": ["MDGL"], "filings": {"recent": {"form": ["8-K", "10-Q"], "filingDate": ["2026-09-01", "2026-08-01"], "accessionNumber": ["a", "b"]}}}
    def fts(self, q, ciks=None, forms="8-K", since=None, until=None, max_hits=100):
        return [{"_id": "0001-24-000001:ex99.htm", "_source": {"ciks": ["0001157601"], "display_names": ["MADRIGAL"], "form": "8-K", "file_type": "EX-99.1",
                 "file_date": "2024-02-28", "adsh": "0001-24-000001", "items": ["8.01"]}}]
    def text(self, url): return TEXT


def test_company_profile_merged_offline():
    from tests.test_fdawatch import FakeCT, FakeFDA
    from fdawatch import core
    from fdawatch.report import profile_markdown
    p = core.company_profile(FakeCT(), FakeFDA(), "Madrigal", today=date(2026, 10, 12), grant_client=FakeGrants(),
                             pubmed_client=FakePM(), rxiv_client=FakeRx(), sec_client=FakeSEC())
    assert p["grants"]["drug_grants_total"] == 1 and p["grants"]["org_grants_total"] == 0  # Madrigal has no RePORTER org
    assert p["papers"]["pubmed_drugs"]["total_since"] == 1 and p["papers"]["preprints"]
    assert p["sec"]["recent_8k_count"] == 1 and p["pdufa"]["candidates"][0]["date"] == "March 14, 2024"
    md = profile_markdown(p)
    assert "UNVERIFIED" in md and "NIH grants" in md and "Preprints" in md
    q = core.company_profile(FakeCT(), FakeFDA(), "Madrigal", today=date(2026, 10, 12))
    assert "grants" not in q and isinstance(q["pdufa"], str)  # basic profile unchanged


@pytest.mark.skipif(not os.environ.get("TRIALWATCH_LIVE"), reason="live API")
def test_live_sources():
    assert g.search_grants(g.ReporterClient(), keyword='"resmetirom"', max_records=5)
    assert pw.search_pubmed(pw.PubMedClient(), drug="resmetirom", max_records=3)["total"] > 50
    rows = sw.pdufa_mentions(sw.SECClient(), "1157601", max_docs=3)
    assert any(c["date_text"].startswith("March 14") for r in rows for c in r["candidates"])
