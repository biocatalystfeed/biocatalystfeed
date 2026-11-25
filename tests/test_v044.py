"""0.4.4: get_paper / get_grant ID lookups (offline, fake clients)."""
from paperwatch.core import classify_paper_id, get_papers
from grantwatch.core import classify_grant_id, get_grants


def test_classify_paper_ids():
    assert classify_paper_id("35658024") == ("pmid", "35658024")
    assert classify_paper_id("PMID: 35658024") == ("pmid", "35658024")
    assert classify_paper_id("https://pubmed.ncbi.nlm.nih.gov/35658024/") == ("pmid", "35658024")
    assert classify_paper_id("https://doi.org/10.1056/NEJMoa2206038") == ("doi", "10.1056/nejmoa2206038")
    assert classify_paper_id("doi:10.1101/2024.01.01.123456") == ("doi", "10.1101/2024.01.01.123456")
    assert classify_paper_id("pmc1234567") == ("pmcid", "PMC1234567")
    assert classify_paper_id("PPR812345") == ("ppr", "PPR812345")
    assert classify_paper_id("semaglutide") is None


class FakePM:
    def __init__(self): self.calls = []
    def esummary(self, ids):
        self.calls.append(list(ids))
        return [{"uid": i, "title": "T" + i, "articleids": [{"idtype": "doi", "value": "10.1/x" + i}], "authors": [],
                 "fulljournalname": "J", "sortpubdate": "2024/01/02 00:00"} for i in ids if i != "999"] + \
               [{"uid": "999", "error": "cannot get document summary"}] * ("999" in ids)


class FakeEPMC:
    def __init__(self): self.queries = []
    def search(self, q, max_records=100):
        self.queries.append(q)
        if "nejmoa" in q.lower():
            return 1, [{"id": "35658024", "source": "MED", "pmid": "35658024", "doi": "10.1056/NEJMoa2206038",
                        "title": "Tirzepatide Once Weekly for the Treatment of Obesity.", "authorString": "Jastreboff AM.",
                        "journalInfo": {"journal": {"title": "N Engl J Med"}}, "firstPublicationDate": "2022-06-04"}]
        return 0, []


def test_get_papers_routes_and_reports_missing():
    pm, ep = FakePM(), FakeEPMC()
    r = get_papers(pm, ep, ["111", "10.1056/NEJMoa2206038", "999", "PMC42", "not an id", "111"])
    assert pm.calls == [["111", "999"]]
    assert [p["requested_id"] for p in r["papers"]] == ["111", "10.1056/NEJMoa2206038"]
    assert r["papers"][0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/111/"
    assert r["papers"][1]["title"].startswith("Tirzepatide") and r["papers"][1]["doi"] == "10.1056/NEJMoa2206038"
    assert r["not_found"] == ["999", "PMC42"] and r["invalid"] == ["not an id"]
    assert any(q.startswith('DOI:"10.1056/nejmoa2206038"') for q in ep.queries)
    assert any(q == 'PMCID:"PMC42"' for q in ep.queries)
    # an unknown PMID falls back to Europe PMC (MEDLINE) once
    assert any(q == 'EXT_ID:"999" AND SRC:MED' for q in ep.queries)


def test_classify_grant_ids():
    assert classify_grant_id("11304574") == ("appl_id", "11304574")
    assert classify_grant_id("5R01CA200994-11") == ("project_num", "5R01CA200994-11")
    assert classify_grant_id("r01 ca200994") == ("project_num", "R01CA200994")
    assert classify_grant_id("https://reporter.nih.gov/project-details/11304574") == ("appl_id", "11304574")
    assert classify_grant_id("cancer") is None


class FakeReporter:
    def __init__(self): self.crits = []
    def search(self, criteria, max_records=500, sort_field="award_notice_date"):
        self.crits.append(criteria)
        mk = lambda a, n, fy: {"appl_id": a, "project_num": n, "core_project_num": n.split("-")[0][1:], "fiscal_year": fy,
                               "project_title": "X", "organization": {"org_name": "U"}, "principal_investigators": []}
        return [mk(11059927, "5R01CA200994-10", 2025), mk(11304574, "5R01CA200994-11", 2026), mk(11304574, "5R01CA200994-11", 2026)]


def test_get_grants_separate_calls_dedupes_and_reports_missing():
    c = FakeReporter()
    r = get_grants(c, ["R01CA200994", "11304574", "U01XX000001", "nope"])
    assert c.crits == [{"appl_ids": [11304574]}, {"project_nums": ["R01CA200994", "U01XX000001"]}]
    assert [g["appl_id"] for g in r["grants"]] == [11304574, 11059927]
    assert r["not_found"] == ["U01XX000001"] and r["invalid"] == ["nope"]
    assert get_grants(c, ["nope"]) == {"grants": [], "not_found": [], "invalid": ["nope"]}


def test_server_json_description_fits_mcp_registry_limit():
    import json, pathlib
    d = json.loads((pathlib.Path(__file__).resolve().parents[1] / "server.json").read_text())
    assert len(d["description"]) <= 100  # MCP Registry rejects longer descriptions (422)
