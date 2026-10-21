"""0.3.0: richer ClinicalTrials.gov diffs (primary endpoints, arms, sites, interventions, results posted) + severity labels."""
from trialwatch.normalize import normalize
from trialwatch.store import Store, diff_records
from trialwatch.severity import severity, shift_days, at_least
from trialwatch.report import markdown


def study(**kw):
    st = {"overallStatus": kw.get("status", "RECRUITING"), "primaryCompletionDateStruct": {"date": kw.get("pcd", "2026-10-01")},
          "startDateStruct": {"date": "2025-01"}}
    if kw.get("results"): st["resultsFirstPostDateStruct"] = {"date": kw["results"]}
    if kw.get("why"): st["whyStopped"] = kw["why"]
    return {"protocolSection": {
        "identificationModule": {"nctId": "NCT01234567", "briefTitle": "Trial"},
        "statusModule": st, "designModule": {"phases": ["PHASE3"], "enrollmentInfo": {"count": kw.get("n", 100)}},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Acme Bio"}},
        "armsInterventionsModule": {"armGroups": [{"label": f"A{i}"} for i in range(kw.get("arms", 2))],
                                    "interventions": [{"type": "DRUG", "name": "acmetide"}]},
        "outcomesModule": {"primaryOutcomes": [{"measure": m} for m in kw.get("outcomes", ["Change in body weight at week 72"])]},
        "contactsLocationsModule": {"locations": [{"facility": f"Site {i}"} for i in range(kw.get("sites", 10))]}}}


def test_normalize_new_fields():
    r = normalize(study(results="2026-09-01", outcomes=["Weight", "HbA1c"]))
    assert r["primary_outcomes"] == "Weight | HbA1c" and r["arm_count"] == 2 and r["site_count"] == 10
    assert r["results_first_posted"] == "2026-09-01"
    bare = normalize({"protocolSection": {"identificationModule": {"nctId": "NCT01234567"}}})
    assert bare["arm_count"] == 0 and bare["site_count"] == 0 and bare["primary_outcomes"] is None


def test_old_snapshot_without_new_fields_is_not_a_change():
    new = normalize(study())
    old = {k: v for k, v in new.items() if k not in ("primary_outcomes", "arm_count", "site_count", "results_first_posted")}
    assert diff_records(old, new) == []


def test_severity_rules():
    S = lambda **c: severity(c)
    assert S(kind="status_change", field="status", old="RECRUITING", new="TERMINATED") == "critical"
    assert S(kind="status_change", field="status", old="RECRUITING", new="COMPLETED") == "notable"
    assert S(kind="field_change", field="why_stopped", old=None, new="Business decision") == "critical"
    assert S(kind="endpoint_change", field="primary_outcomes", old="a", new="b") == "critical"
    assert S(kind="enrollment_change", field="enrollment", old="100", new="70") == "notable"
    assert S(kind="enrollment_change", field="enrollment", old="100", new="95") == "minor"
    assert S(kind="date_change", field="primary_completion_date", old="2026-10-01", new="2027-10") == "notable"
    assert S(kind="date_change", field="primary_completion_date", old="2026-10-01", new="2026-10-15") == "minor"
    assert S(kind="site_change", field="site_count", old="18", new="23") == "minor"
    assert S(kind="arm_change", field="arm_count", old="2", new="3") == "notable"
    assert S(kind="new_trial", field=None, old=None, new="RECRUITING") == "notable"
    assert shift_days("2026-10-01", "2027-10") == 365 and shift_days("2026-10", "bad") is None


def test_store_end_to_end_with_severity(tmp_path):
    st = Store(str(tmp_path / "t.db"))
    st.ingest("w", [normalize(study())], now="2026-10-20T00:00:00+00:00")
    st.ingest("w", [normalize(study(status="TERMINATED", why="Sponsor decision", pcd="2027-04-01", sites=12, n=60,
                                    outcomes=["Change in body weight at week 52"], results="2026-10-20"))], now="2026-10-21T00:00:00+00:00")
    ch = st.changes(watch="w")
    by = {c["field"]: c for c in ch}
    assert by["status"]["severity"] == "critical" and by["primary_outcomes"]["kind"] == "endpoint_change"
    assert by["primary_completion_date"]["shift_days"] == 182 and by["site_count"]["severity"] == "minor"
    assert by["results_first_posted"]["kind"] == "results_posted"
    crit = st.changes(watch="w", min_severity="critical")
    assert {c["field"] for c in crit} == {"status", "why_stopped", "primary_outcomes"}
    assert len(at_least(ch, "notable")) < len(ch)
    md = markdown("t", st.trials("w"), ch)
    assert "| Severity |" in md and md.index("critical") < md.index("minor")


def test_digest_titles_carry_severity():
    from biowatch.digest import _title
    assert _title({"kind": "status_change", "severity": "critical", "nct_id": "NCT01234567", "field": "status",
                   "old": "RECRUITING", "new": "TERMINATED"}).startswith("[critical status_change]")
