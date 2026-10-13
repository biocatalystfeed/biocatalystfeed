import copy, os, pytest
from datetime import date
from fdawatch.client import build_drugsfda_search, build_label_search, OpenFDAClient
from fdawatch.normalize import submissions, label, is_novel
from fdawatch.store import FDAStore
from fdawatch.aliases import resolve
from fdawatch import core
from fdawatch.report import profile_markdown

APP = {"application_number": "NDA217785", "sponsor_name": "MADRIGAL",
       "products": [{"brand_name": "REZDIFFRA", "active_ingredients": [{"name": "RESMETIROM"}]}],
       "submissions": [
           {"submission_type": "ORIG", "submission_number": "1", "submission_status": "AP", "submission_status_date": "20240314",
            "review_priority": "PRIORITY", "submission_class_code_description": "Type 1 - New Molecular Entity",
            "application_docs": [{"type": "Label", "date": "20240517", "url": "u1"}]},
           {"submission_type": "SUPPL", "submission_number": "6", "submission_status": "AP", "submission_status_date": "20260724",
            "submission_class_code_description": "Labeling", "application_docs": []}]}
LABEL = {"set_id": "abc", "version": "4", "effective_time": "20260729",
         "openfda": {"brand_name": ["Rezdiffra"], "manufacturer_name": ["Madrigal Pharmaceuticals, Inc."], "application_number": ["NDA217785"]}}


def test_normalize_submissions():
    rows = submissions(APP)
    assert [r["key"] for r in rows] == ["NDA217785:ORIG1", "NDA217785:SUPPL6"]
    o = rows[0]
    assert o["submission_status"] == "APPROVED" and o["submission_status_date"] == "2024-03-14" and o["label_url"] == "u1"
    assert o["brand_names"] == "REZDIFFRA" and o["active_ingredients"] == "RESMETIROM"
    assert is_novel(o) and not is_novel(rows[1])
    assert label(LABEL)["effective_time"] == "2026-07-29" and label(LABEL)["brand_name"] == "Rezdiffra"


def test_bla_novelty():
    base = {"submission_type": "ORIG", "submission_status": "APPROVED", "submission_number": "1"}
    assert is_novel({**base, "application_number": "BLA761408", "submission_class": None})
    assert not is_novel({**base, "application_number": "BLA761481", "submission_class": "Type 5 - New Formulation or New Manufacturer"})


def test_search_builders():
    s = build_drugsfda_search(["LILLY", "ELI LILLY AND CO"], since="2026-09-01")
    assert s == '(sponsor_name:"LILLY"+OR+sponsor_name:"ELI LILLY AND CO")+AND+submissions.submission_status_date:[20260901+TO+29991231]'
    assert build_label_search(["Madrigal Pharmaceuticals, Inc."]) == '(openfda.manufacturer_name:"Madrigal Pharmaceuticals, Inc.")'
    with pytest.raises(ValueError): build_drugsfda_search()


def test_aliases():
    t = resolve("Terns Pharmaceuticals")
    assert t["known"] and "Terns, Inc." in t["ct_queries"]
    assert resolve("TERN")["canonical"] == resolve("terns, inc.")["canonical"] == "Terns Pharmaceuticals"
    assert resolve("Lilly")["fda_sponsors"][0] == "LILLY" and resolve("LLY")["canonical"] == "Eli Lilly"
    u = resolve("Acme Bio Inc")
    assert not u["known"] and u["ct_queries"] == ["Acme Bio Inc"] and u["fda_sponsors"] == ["ACME"]


def test_store_changes(tmp_path):
    st = FDAStore(str(tmp_path / "f.db"))
    rows = submissions(APP)
    assert st.ingest("w", rows, [label(LABEL)], now="2026-10-01")["baseline"]
    app2 = copy.deepcopy(APP)
    app2["submissions"].append({"submission_type": "SUPPL", "submission_number": "7", "submission_status": "AP",
                                "submission_status_date": "20261010", "submission_class_code_description": "Efficacy"})
    app2["submissions"][1]["application_docs"] = [{"type": "Letter", "date": "20260728"}]
    lab2 = dict(LABEL, version="5", effective_time="20261005")
    info = st.ingest("w", submissions(app2), [label(lab2)], now="2026-10-11")
    kinds = {(c["key"], c["kind"]) for c in st.changes(watch="w", run_id=info["run_id"])}
    assert ("NDA217785:SUPPL7", "new_submission") in kinds
    assert ("NDA217785:SUPPL6", "new_documents") in kinds
    assert ("abc", "label_revision") in kinds
    assert st.changes(since="2026-10-05") and not st.changes(since="2026-10-12")


class FakeFDA:
    def drugsfda(self, sponsors=None, **kw):
        return [APP, dict(APP, application_number="NDA999", sponsor_name="MADRIGAL HOLDINGS OTHER")]
    def labels(self, manufacturers=None, **kw):
        return [LABEL]


class FakeCT:
    def search(self, max_records=100, sponsor=None, **kw):
        lead = {"Terns, Inc.": "Terns, Inc., a subsidiary of Merck & Co., Inc. (Rahway, New Jersey USA)"}.get(sponsor, "Other Univ")
        st = {"protocolSection": {"identificationModule": {"nctId": f"NCT{abs(hash(sponsor)) % 10**8:08d}", "briefTitle": "x"},
                                  "statusModule": {"overallStatus": "RECRUITING", "primaryCompletionDateStruct": {"date": "2027-01"}},
                                  "sponsorCollaboratorsModule": {"leadSponsor": {"name": lead}}, "designModule": {"phases": ["PHASE1"]}}}
        return [st]


def test_company_profile_offline():
    p = core.company_profile(FakeCT(), FakeFDA(), "Madrigal", today=date(2026, 10, 12))
    assert p["company"] == "Madrigal Pharmaceuticals" and p["fda"]["applications"] == 1  # exact-sponsor filter drops NDA999
    assert p["fda"]["novel_approvals"][0]["brand_names"] == "REZDIFFRA"
    assert [x["submission_type"] for x in p["fda"]["recent_submissions"]] == ["SUPPL"]
    assert p["trials"]["total"] == 0  # FakeCT lead sponsor isn't Madrigal -> filtered out
    t = core.company_profile(FakeCT(), FakeFDA(), "Terns Pharmaceuticals", today=date(2026, 10, 12))
    assert t["trials"]["total"] == 1 and t["fda"]["applications"] == 0
    assert "Terns Pharmaceuticals" in profile_markdown(t)


@pytest.mark.skipif(not os.environ.get("TRIALWATCH_LIVE"), reason="live API")
def test_live_madrigal():
    rows = core.fda_approvals(OpenFDAClient(), sponsor="MDGL")
    assert any(r["brand_names"] == "REZDIFFRA" and r["submission_type"] == "ORIG" for r in rows)
