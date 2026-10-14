"""Offline tests for the launch-prep work: filters, Europe PMC, PI matching, grant sorting, digests, branding, actor."""
import json, os, pathlib, re, subprocess, sys
import xml.etree.ElementTree as ET
import pytest
from biowatch import filters, digest
from grantwatch import core as g
from paperwatch import core as pw
from secwatch import core as sw

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------- exclude / rank / dedup ----------
def test_exclude_whole_words():
    rows = [{"title": "Resmetirom in mice"}, {"title": "Resmetirom in humans"}, {"title": "Micelle formulation"}]
    assert [r["title"] for r in filters.exclude(rows, ["mice"])] == ["Resmetirom in humans", "Micelle formulation"]
    assert filters.exclude(rows, None) == rows
    assert len(filters.exclude(rows, ["IN HUMANS"])) == 2  # case-insensitive phrase


def test_rank_title_weighting():
    rows = [{"title": "Liver outcomes", "journal": "resmetirom review", "date": "2026-10-01"},
            {"title": "Resmetirom and liver fat", "date": "2026-01-01"},
            {"title": "Unrelated", "date": "2026-12-01"}]
    r = filters.rank(rows, '"resmetirom"[tiab] OR liver')
    assert [x["title"] for x in r] == ["Resmetirom and liver fat", "Liver outcomes", "Unrelated"]
    assert r[0]["relevance"] == 8 and r[2]["relevance"] == 0
    assert filters.query_terms('("A b"[ad]) AND (VK2735)', ["x"]) == ["a b", "vk2735"]


def test_dedup_by_doi_and_pmid():
    rows = [{"key": "doi:10.1101/x", "source": "biorxiv", "doi": "10.1101/X", "title": "pre", "published_doi": "10.1/j"},
            {"key": "doi:10.1101/x", "source": "europepmc", "doi": "https://doi.org/10.1101/x", "title": "pre (epmc)"},
            {"key": "pmid:5", "source": "pubmed", "id": "5", "doi": "10.1/J", "title": "journal version"},
            {"key": "doi:10.2/z", "source": "europepmc", "pmid": "5", "doi": None, "title": "same pmid"},
            {"key": "pmid:6", "source": "pubmed", "id": "6", "title": "other"}]
    d = filters.dedup(rows)
    assert len(d) == 2
    j = next(x for x in d if x.get("id") == "5")
    assert j["title"] == "journal version" and set(j["sources"]) == {"pubmed", "europepmc", "biorxiv"}  # preprint's published DOI


# ---------- Europe PMC ----------
EPMC_PPR = {"id": "PPR1", "source": "PPR", "doi": "10.1101/2026.10.01.1", "title": "Resmetirom preprint.", "authorString": "A B, C D.",
            "firstPublicationDate": "2026-10-02", "bookOrReportDetails": {"publisher": "bioRxiv"}, "versionNumber": 2}
EPMC_MED = {"id": "77", "source": "MED", "pmid": "77", "doi": "10.5/abc", "title": "Journal paper", "authorString": "X Y.",
            "firstPublicationDate": "2026-09-01", "journalInfo": {"journal": {"title": "Hepatology"}}}


def test_epmc_query_and_normalize():
    q = pw.epmc_query(affiliation=["Madrigal"], drug="resmetirom", since="2026-10-01", until="2026-10-12", preprints="rxiv")
    assert q.startswith('(AFF:"Madrigal") AND ((TITLE:"resmetirom" OR ABSTRACT:"resmetirom" OR CHEM:"resmetirom"))')
    assert "FIRST_PDATE:[2026-10-01 TO 2026-10-12]" in q and 'PUBLISHER:"bioRxiv"' in q
    with pytest.raises(ValueError): pw.epmc_query()
    p = pw.norm_epmc(EPMC_PPR)
    assert p["origin"] == "biorxiv" and p["key"] == "doi:10.1101/2026.10.01.1" and p["is_preprint"] and p["version"] == "2"
    assert p["title"] == "Resmetirom preprint" and p["url"] == "https://doi.org/10.1101/2026.10.01.1"
    m = pw.norm_epmc(EPMC_MED)
    assert m["pmid"] == "77" and m["journal"] == "Hepatology" and m["url"].endswith("/MED/77")


class FakeEPMC:
    def __init__(self, fail=False): self.fail, self.queries = fail, []
    def search(self, q, max_records=100):
        if self.fail: raise RuntimeError("down")
        self.queries.append(q)
        return (1, [EPMC_PPR]) if "SRC:PPR" in q else (1, [EPMC_MED])


def test_fast_preprints_and_fallback():
    from tests.test_biowatch import FakeRx
    e = FakeEPMC()
    r = pw.search_preprints_fast(e, FakeRx(), drug=["resmetirom"], until="2026-10-12")
    assert r[0]["source"] == "biorxiv" and r[0]["via"] == "europepmc" and len(e.queries) == 1
    r = pw.search_preprints_fast(FakeEPMC(fail=True), FakeRx(), drug=["resmetirom"], until="2026-10-12")
    assert r and r[0]["key"].startswith("doi:10.1101/biorxiv")  # fell back to bioRxiv API
    with pytest.raises(RuntimeError): pw.search_preprints_fast(FakeEPMC(fail=True), None, drug="x")


def test_search_all_merges_sources():
    from tests.test_biowatch import FakePM
    class PM(FakePM):
        def esummary(self, ids): return [{"uid": "77", "title": "Journal paper", "authors": [], "sortpubdate": "2026/09/01",
                                         "articleids": [{"idtype": "doi", "value": "10.5/ABC"}]}]
    res = pw.search_all(PM(), FakeEPMC(), None, drug="resmetirom", preprint_days=7, exclude=["unrelated"], rank=True)
    keys = {(tuple(sorted(p["sources"])), p["title"]) for p in res["papers"]}
    assert (("europepmc", "pubmed"), "Journal paper") in keys and (("biorxiv",), "Resmetirom preprint") in keys
    assert len(res["papers"]) == 2 and not res["errors"]


def test_paper_watch_with_epmc(tmp_path):
    st = pw.store(str(tmp_path / "p.db"))
    i1 = pw.run_watch(None, None, st, "w", drug="resmetirom", epmc=FakeEPMC(), preprint_days=7)
    assert i1["baseline"] and i1["records"] == 2
    i2 = pw.run_watch(None, None, st, "w", drug="resmetirom", epmc=FakeEPMC(), preprint_days=7, exclude=["preprint"])
    assert i2["records"] == 1 and not i2["changes_detail"]


# ---------- grants ----------
def test_parse_name_and_pi_matching():
    assert g.parse_name("Doe, Jane A.") == {"first": "jane", "middle": "a", "last": "doe"}
    assert g.parse_name("Jane Alice Doe") == {"first": "jane", "middle": "alice", "last": "doe"}
    ja = {"first_name": "Jane", "middle_name": "A", "last_name": "Doe"}
    jb = {"first_name": "Jane", "middle_name": "B", "last_name": "Doe"}
    jn = {"first_name": "Jane", "middle_name": "", "last_name": "Doe"}
    jo = {"first_name": "Janet", "middle_name": "A", "last_name": "Doe"}
    assert g.pi_matches(ja, "Jane A. Doe") and not g.pi_matches(jb, "Jane A. Doe") and not g.pi_matches(jo, "Jane A Doe")
    assert g.pi_matches(jn, "Jane A Doe") and not g.pi_matches(jn, "Jane A Doe", exact=True)
    assert g.pi_matches(jb, "Doe, Jane") and not g.pi_matches(jb, "Doe, Jane", exact=True)
    assert g.pi_matches(ja, "J Doe") and not g.pi_matches(ja, "J Doe", exact=True)
    assert g.pi_matches({"full_name": "Jane A. Doe"}, "Jane A Doe")
    assert g.build_criteria(pi="Jane A. Doe")["pi_names"] == [{"first_name": "jane", "last_name": "doe"}]


def test_search_grants_pi_filter_sort_future_exclude():
    from tests.test_biowatch import RAW_GRANT
    base = dict(RAW_GRANT, principal_investigators=[{"first_name": "Jane", "middle_name": "A", "last_name": "Doe", "full_name": "Jane A Doe"}])
    recs = [dict(base, appl_id=1, award_notice_date="2026-05-01"),
            dict(base, appl_id=2, award_notice_date="2027-04-01", project_title="Future FY award"),
            dict(base, appl_id=3, award_notice_date="2026-09-01", principal_investigators=[{"first_name": "Jane", "middle_name": "B", "last_name": "Doe"}]),
            dict(base, appl_id=4, award_notice_date="2026-08-01", project_title="Resmetirom mouse model")]
    class C:
        def search(self, criteria, max_records=500, sort_field=None): return recs
    r = g.search_grants(C(), pi="Jane A. Doe", today="2026-10-12")
    assert [x["key"] for x in r] == ["4", "1", "2"] and r[-1]["future_dated"]  # B-initial PI dropped; future last
    assert [x["key"] for x in g.search_grants(C(), pi="Jane A. Doe", today="2026-10-12", include_future=False, exclude=["mouse"])] == ["1"]
    assert [x["key"] for x in g.search_grants(C(), keyword="mouse model", today="2026-10-12", rank=True)][0] == "4"


# ---------- secwatch ----------
def test_sec_private_company_message_and_ua(monkeypatch):
    r = sw.company_sec(object(), {"canonical": "Zealand Pharma", "sec_cik": None, "ticker": None})
    assert r["not_sec_registered"] and "Zealand Pharma" in r["message"] and "privately held" in r["message"]
    monkeypatch.delenv("SEC_USER_AGENT", raising=False); monkeypatch.delenv("BIOCATALYSTFEED_CONTACT", raising=False)
    assert sw.user_agent() == "BioCatalystFeed/0.2 contact@biocatalystfeed.com"
    monkeypatch.setenv("BIOCATALYSTFEED_CONTACT", "ops@example.com")
    assert sw.user_agent().endswith("ops@example.com") and sw.SECClient().s.headers["User-Agent"].endswith("ops@example.com")
    monkeypatch.setenv("SEC_USER_AGENT", "X y@z")
    assert sw.user_agent() == "X y@z"


def test_profile_private_company():
    from datetime import date
    from tests.test_fdawatch import FakeCT, FakeFDA
    from tests.test_biowatch import FakeSEC
    from fdawatch import core
    from fdawatch.report import profile_markdown
    p = core.company_profile(FakeCT(), FakeFDA(), "Zealand Pharma", today=date(2026, 10, 12), sec_client=FakeSEC())
    assert p["sec"]["not_sec_registered"] and p["pdufa"].startswith("Not available:")
    assert "no SEC CIK" in profile_markdown(p)


# ---------- digests ----------
CH = [{"id": 1, "run_id": 2, "watch": "w", "key": "pmid:2", "kind": "new_paper", "field": None, "old": None, "new": None,
       "title": "A & B <study>", "url": "https://x/2", "detected_at": "2026-10-12T00:00:00+00:00"},
      {"id": 2, "run_id": 2, "watch": "t", "nct_id": "NCT1", "kind": "status_change", "field": "status", "old": "RECRUITING",
       "new": "TERMINATED", "detected_at": "2026-10-12T01:00:00"}]


def test_rss_and_json_feed(tmp_path):
    root = ET.fromstring(digest.rss("Feed", CH).split("\n", 1)[1])
    items = root.findall("./channel/item")
    assert len(items) == 2 and items[0].find("title").text == "[new_paper] A & B <study>"
    assert items[1].find("link").text == "https://clinicaltrials.gov/study/NCT1" and "Not investment" in root.find("./channel/description").text
    jf = digest.json_feed("Feed", CH)
    assert jf["version"].endswith("1.1") and jf["items"][1]["title"] == "[status_change] NCT1: status RECRUITING -> TERMINATED"
    assert len({i["id"] for i in jf["items"]}) == 2
    digest.write(CH, "Feed", str(tmp_path / "a.rss"), str(tmp_path / "a.json"))
    assert json.load(open(tmp_path / "a.json"))["title"] == "Feed" and (tmp_path / "a.rss").read_text().startswith("<?xml")


def test_cli_watch_writes_feeds(tmp_path, monkeypatch):
    from paperwatch import cli
    monkeypatch.setattr(cli, "EuropePMCClient", FakeEPMC)
    db, rss = str(tmp_path / "b.db"), str(tmp_path / "f.rss")
    args = ["--db", db, "watch", "--name", "w", "--drug", "resmetirom", "--sources", "europepmc", "preprints", "--rss", rss]
    cli.main(args); cli.main(args)
    assert "<rss" in open(rss).read()


# ---------- branding / packaging ----------
def test_bcf_cli_dispatch(capsys):
    from biocatalystfeed import cli, __version__
    assert cli.main([]) == 0 and "BioCatalystFeed" in capsys.readouterr().out
    assert cli.main(["nope"]) == 2
    with pytest.raises(SystemExit): cli.main(["grants", "--help"])
    assert "grantwatch" in capsys.readouterr().out
    assert __version__ == "0.2.2"


def test_license_notice_docs_present():
    assert "Apache License" in (ROOT / "LICENSE").read_text() and "Version 2.0" in (ROOT / "LICENSE").read_text()
    n = (ROOT / "NOTICE").read_text()
    for s in ("National Library of Medicine", "open.fda.gov", "NIH RePORTER", "PubMed", "Europe PMC", "bioRxiv"): assert s in n
    for f in ("TERMS.md", "PRIVACY.md"): assert "DRAFT, NOT LEGAL ADVICE" in (ROOT / f).read_text()
    assert "Not investment, legal or medical advice" in (ROOT / "README.md").read_text()
    assert 'license = "Apache-2.0"' in (ROOT / "pyproject.toml").read_text()


def test_no_personal_contact_in_code():
    hits = subprocess.run(["git", "grep", "-n", "-I", "-E", r"mail\.grokbot\.com", "--", "*.py", "actor", "pyproject.toml"],
                          cwd=ROOT, capture_output=True, text=True).stdout
    assert hits == "", hits


# ---------- Apify actor ----------
def test_actor_self_contained_and_in_sync():
    sys.path.insert(0, str(ROOT / "scripts"))
    import sync_actor
    assert sync_actor.main(check=True) == 0, "run: python scripts/sync_actor.py"
    df = (ROOT / "actor" / "Dockerfile").read_text()
    for line in df.splitlines():
        if line.startswith("COPY"):
            for src in line.split()[1:-1]: assert (ROOT / "actor" / src).exists(), src  # context = actor/
    aj = json.loads((ROOT / "actor/.actor/actor.json").read_text())
    assert (ROOT / "actor/.actor" / aj["dockerfile"]).resolve() == (ROOT / "actor/Dockerfile").resolve()
    assert (ROOT / "actor/.actor" / aj["dockerContextDir"]).resolve() == (ROOT / "actor").resolve()
    assert (ROOT / "actor/.actor" / aj["input"]).exists()


EDITORS = {"string": {"textfield", "textarea", "select", "datepicker", "hidden", "javascript", "python", "json"},
           "integer": {"number", "hidden"}, "array": {"stringList", "requestListSources", "json", "keyValue", "select", "hidden"},
           "boolean": {"checkbox", "hidden"}, "object": {"json", "hidden"}}


def _validate(schema, inp):
    errs = []
    for k, v in inp.items():
        p = schema["properties"].get(k)
        if p is None: errs.append(f"unknown {k}"); continue
        t = {"string": str, "integer": int, "array": list, "boolean": bool, "object": dict}[p["type"]]
        if not isinstance(v, t): errs.append(f"{k} type"); continue
        if "enum" in p and v not in p["enum"]: errs.append(f"{k} enum")
        if "pattern" in p and not re.search(p["pattern"], v): errs.append(f"{k} pattern")
        if "minimum" in p and v < p["minimum"] or "maximum" in p and v > p["maximum"]: errs.append(f"{k} range")
    errs += [f"missing {k}" for k in schema.get("required", []) if k not in inp]
    return errs


def test_actor_input_schema_valid():
    s = json.loads((ROOT / "actor/.actor/input_schema.json").read_text())
    assert s["schemaVersion"] == 1 and s["type"] == "object" and s["title"] and s["properties"]
    for k, p in s["properties"].items():
        assert p.get("title") and p.get("description") and p.get("type") in EDITORS, k
        if p["type"] == "string" or "editor" in p: assert p.get("editor") in EDITORS[p["type"]], k
        if "enum" in p:
            assert p.get("default", p["enum"][0]) in p["enum"]
            if "enumTitles" in p: assert len(p["enumTitles"]) == len(p["enum"])
        if "pattern" in p: re.compile(p["pattern"])
        if "default" in p: assert not _validate(s, {k: p["default"]}), k
        if "prefill" in p: assert not _validate(s, {k: p["prefill"]}), k
    assert set(s.get("required", [])) <= set(s["properties"])
    assert not _validate(s, json.loads((ROOT / "actor/input.json").read_text()))
    assert _validate(s, {"maxRecords": 0, "outputMode": "x", "changedSince": "10/12/2026", "bogus": 1}) == \
        ["maxRecords range", "outputMode enum", "changedSince pattern", "unknown bogus"]


def test_actor_execute_offline(tmp_path):
    import importlib.util
    from tests.test_fdawatch import FakeCT
    spec = importlib.util.spec_from_file_location("actor_main", ROOT / "actor/main.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    db = str(tmp_path / "a.db")
    out = m.execute({"watchName": "v", "sponsor": "Viking Therapeutics"}, db, client=FakeCT())
    assert len(out) == 1 and out[0]["nct_id"].startswith("NCT")
    assert m.execute({"watchName": "v", "sponsor": "Viking Therapeutics"}, db, client=FakeCT()) == []
    assert m.execute({"watchName": "v", "sponsor": "Viking Therapeutics", "outputMode": "trials", "excludeTerms": ["x"]}, db, client=FakeCT()) == []
    with pytest.raises(ValueError): m.execute({}, db, client=FakeCT())
