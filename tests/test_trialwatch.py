import copy, os, pytest
from trialwatch.client import CTGovClient
from trialwatch.normalize import normalize
from trialwatch.store import Store, diff_records
from trialwatch.report import sponsor_pipeline, markdown

STUDY = {"protocolSection": {
    "identificationModule": {"nctId": "NCT00000001", "briefTitle": "Test GLP-1 study"},
    "statusModule": {"overallStatus": "RECRUITING", "lastUpdatePostDateStruct": {"date": "2026-10-01"},
                     "primaryCompletionDateStruct": {"date": "2027-06"}},
    "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Acme Bio", "class": "INDUSTRY"}},
    "designModule": {"phases": ["PHASE2"], "enrollmentInfo": {"count": 100, "type": "ESTIMATED"}},
    "conditionsModule": {"conditions": ["Obesity"]},
    "armsInterventionsModule": {"interventions": [{"type": "DRUG", "name": "AC-1"}]}}}


def test_normalize():
    r = normalize(STUDY)
    assert r["nct_id"] == "NCT00000001" and r["phase"] == "PHASE2" and r["enrollment"] == 100
    assert r["lead_sponsor"] == "Acme Bio" and r["interventions"] == "DRUG:AC-1"


def test_params():
    p = CTGovClient.build_params(sponsor="Acme", phases=["phase2", "PHASE3"], statuses=["recruiting"], changed_since="2026-01-01")
    assert p["query.spons"] == "Acme" and p["filter.overallStatus"] == "RECRUITING"
    assert "AREA[Phase]PHASE2 OR AREA[Phase]PHASE3" in p["filter.advanced"]
    assert "AREA[LastUpdatePostDate]RANGE[2026-01-01,MAX]" in p["filter.advanced"]
    with pytest.raises(ValueError):
        CTGovClient.build_params(phases=["PHASE9"])


def test_diff_and_store(tmp_path):
    st = Store(str(tmp_path / "t.db"))
    base = normalize(STUDY)
    i1 = st.ingest("w", [base], now="2026-10-01T00:00:00")
    assert i1["baseline"] and i1["changes"] == 0
    s2 = copy.deepcopy(STUDY)
    s2["protocolSection"]["statusModule"]["overallStatus"] = "TERMINATED"
    s2["protocolSection"]["statusModule"]["whyStopped"] = "Business decision"
    s2["protocolSection"]["designModule"]["phases"] = ["PHASE3"]
    s2["protocolSection"]["designModule"]["enrollmentInfo"]["count"] = 40
    s2["protocolSection"]["statusModule"]["primaryCompletionDateStruct"]["date"] = "2026-11"
    new = copy.deepcopy(STUDY); new["protocolSection"]["identificationModule"]["nctId"] = "NCT00000002"
    i2 = st.ingest("w", [normalize(s2), normalize(new)], now="2026-10-08T00:00:00")
    kinds = {(c["kind"], c["field"]) for c in st.changes(watch="w", since="2026-10-02")}
    assert ("status_change", "status") in kinds and ("phase_change", "phase") in kinds
    assert ("enrollment_change", "enrollment") in kinds and ("date_change", "primary_completion_date") in kinds
    assert ("new_trial", None) in kinds and i2["changes"] == 6
    sc = [c for c in st.changes(watch="w") if c["kind"] == "status_change"][0]
    assert (sc["old"], sc["new"]) == ("RECRUITING", "TERMINATED")
    assert st.ingest("w", [normalize(s2), normalize(new)])["changes"] == 0
    assert "TERMINATED" in markdown("t", st.trials("w"), st.changes(watch="w"))


def test_pipeline():
    p = sponsor_pipeline([normalize(STUDY)])
    assert p["total"] == 1 and p["by_phase"] == {"PHASE2": 1} and len(p["active"]) == 1


@pytest.mark.skipif(not os.environ.get("TRIALWATCH_LIVE"), reason="set TRIALWATCH_LIVE=1 for network test")
def test_live():
    r = normalize(CTGovClient().get("NCT07868939"))
    assert r["nct_id"] == "NCT07868939"
