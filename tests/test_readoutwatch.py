"""Offline tests for readoutwatch (readout calendar, watch, Trials at Risk, page), provenance and digests."""
import json
from biowatch import digest, provenance as pv
from readoutwatch import core as rc, page, risk

TODAY = "2026-10-28"


def study(nct, pcd, typ="ESTIMATED", status="RECRUITING", sponsor="Viking Therapeutics, Inc.", enr=100, etype="ESTIMATED", upd="2026-09-01", why=None):
    return {"protocolSection": {
        "identificationModule": {"nctId": nct, "briefTitle": f"Trial {nct}"},
        "statusModule": {"overallStatus": status, "whyStopped": why, "primaryCompletionDateStruct": {"date": pcd, "type": typ},
                         "lastUpdatePostDateStruct": {"date": upd}},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor, "class": "INDUSTRY"}},
        "designModule": {"phases": ["PHASE3"], "enrollmentInfo": {"count": enr, "type": etype}},
        "conditionsModule": {"conditions": ["Obesity"]}}}


class FakeCT:
    def __init__(self, studies): self.studies = studies; self.calls = []
    def _get(self, path, p):
        self.calls.append(p)
        adv = p["filter.advanced"]
        st = set(p.get("filter.overallStatus", "").split(","))
        field = "LastUpdatePostDate" if "AREA[LastUpdatePostDate]" in adv else "PrimaryCompletionDate"
        lo, hi = adv.split(f"AREA[{field}]RANGE[")[1].split("]")[0].split(",")
        out = []
        for s in self.studies:
            sm = s["protocolSection"]["statusModule"]
            d = sm["lastUpdatePostDateStruct"]["date"] if field != "PrimaryCompletionDate" else sm["primaryCompletionDateStruct"]["date"]
            if sm["overallStatus"] in st and (lo == "MIN" or d >= lo) and (hi == "MAX" or d <= hi): out.append(s)
        return {"studies": out}


def test_params_window_and_filters():
    p = rc.params("Viking", "obesity", None, ["PHASE3"], rc.ACTIVE, "2026-10-28", "2027-01-26", True)
    assert "AREA[PrimaryCompletionDate]RANGE[2026-10-28,2027-01-26]" in p["filter.advanced"]
    assert "AREA[LeadSponsorClass]INDUSTRY" in p["filter.advanced"] and "AREA[Phase]PHASE3" in p["filter.advanced"]
    assert p["sort"] == "PrimaryCompletionDate:asc" and p["query.cond"] == "obesity"
    assert rc._window(None, None, None, TODAY) == (TODAY, "2027-01-26")


def test_readouts_provenance_and_ticker():
    ct = FakeCT([study("NCT00000002", "2026-12-01"), study("NCT00000001", "2026-11-01", sponsor="Unknown Bio GmbH"),
                 study("NCT00000003", "2028-01-01")])
    rows = rc.readouts(ct, today=TODAY)
    assert [r["nct_id"] for r in rows] == ["NCT00000001", "NCT00000002"]
    v = rows[1]
    assert v["ticker"] == "VKTX" and v["ticker_confidence"] == 0.95 and v["ticker_method"] == "alias_table"
    assert rows[0]["ticker"] is None and rows[0]["ticker_confidence"] == 0.0
    assert v["source_url"] == "https://clinicaltrials.gov/api/v2/studies/NCT00000002" and v["verified_as_of"].endswith("Z")
    assert v["verify_hash"].startswith("sha256:") and pv.check(v)
    v2 = dict(v, verified_as_of="2030-01-01T00:00:00Z"); assert pv.check(v2)  # timestamp not part of the hash
    v2["readout_date"] = "2027-01-01"; assert not pv.check(v2)
    assert rc.readouts(ct, today=TODAY, ticker_only=True)[0]["nct_id"] == "NCT00000002"


def test_watch_detects_slip_and_risk(tmp_path):
    db = str(tmp_path / "w.db")
    ct = FakeCT([study("NCT00000002", "2026-12-01", enr=300)])
    assert rc.run_watch(ct, rc.store(db), "w", today=TODAY)["baseline"]
    ct.studies = [study("NCT00000002", "2027-08-01", enr=200)]
    info = rc.run_watch(ct, rc.store(db), "w", since=TODAY, until="2027-12-31", today=TODAY)
    kinds = {c["kind"]: c for c in info["changes_detail"]}
    assert kinds["readout_date_change"]["direction"] == "delayed" and "enrollment_change" in kinds
    ct.studies += [study("NCT00000009", "2026-09-01", upd="2025-01-01"),
                   study("NCT00000010", "2027-03-01", status="TERMINATED", upd="2026-10-01", why="business decision")]
    rows = risk.trials_at_risk(ct, db_path=db, today=TODAY)
    by = {r["nct_id"]: {f["flag"] for f in r["risk_flags"]} for r in rows}
    assert by["NCT00000010"] == {"stopped"} and by["NCT00000009"] == {"overdue", "stale_overdue"}
    assert {"delayed", "enrollment_cut"} <= by["NCT00000002"]
    assert rows[0]["risk_score"] >= rows[-1]["risk_score"] and all(pv.check(r) for r in rows)
    assert risk.trials_at_risk(ct, db_path=db, today=TODAY, flags=["stopped"])[0]["nct_id"] == "NCT00000010"


def test_enrollment_shortfall(tmp_path):
    db = str(tmp_path / "e.db")
    ct = FakeCT([study("NCT00000004", "2026-11-15", enr=400)])
    rc.run_watch(ct, rc.store(db), "w", today=TODAY)
    ct.studies = [study("NCT00000004", "2026-11-15", status="ACTIVE_NOT_RECRUITING", enr=150, etype="ACTUAL")]
    rc.run_watch(ct, rc.store(db), "w", today=TODAY)
    r = risk.trials_at_risk(ct, db_path=db, today=TODAY)
    f = {x["flag"]: x for x in r[0]["risk_flags"]}
    assert "enrollment_shortfall" in f and "37%" in f["enrollment_shortfall"]["detail"]


def test_ticker_match_sec_list():
    pv.load_sec_tickers(data={"0": {"ticker": "AARD", "title": "Aardvark Therapeutics, Inc."}, "1": {"ticker": "MRK", "title": "Merck & Co., Inc."}})
    assert pv.ticker_match("Aardvark Therapeutics Inc")["ticker_confidence"] == 0.9
    assert pv.ticker_match("Merck Sharp & Dohme LLC")["ticker_method"] == "sec_prefix_name"
    assert pv.ticker_match("Merck KGaA, Darmstadt, Germany")["ticker"] is None
    assert pv.ticker_match("X", "ABC")["ticker_confidence"] == 1.0
    pv._SEC_NAMES = None


def test_digest_markdown_html_and_page():
    ct = FakeCT([study("NCT00000002", "2026-12-01")])
    rows = rc.readouts(ct, today=TODAY)
    md = digest.markdown("Readouts", rows)
    assert "NCT00000002" not in md or "clinicaltrials.gov" in md
    assert "2026-12-01" in md and "VKTX" in md and "(source)" in md.replace("[source]", "(source)")
    h = digest.html("Readouts <x>", rows)
    assert "<!doctype html>" in h and "Readouts &lt;x&gt;" in h and "2026-12-01" in h
    data = page.payload(rows, "2026-10-28T00:00:00Z", [TODAY, "2027-01-26"], {})
    out = page.render(data)
    assert "Trial readout calendar" in out and "NCT00000002" in out and "calendar.json" in out
    j = json.loads(out.split('type="application/json">')[1].split("</script>")[0].replace("<\\/", "</"))
    assert j["events"][0]["verify_hash"].startswith("sha256:")


def test_mcp_tools_registered_with_descriptions():
    import asyncio
    from trialwatch import mcp_server as m
    tools = {t.name: t for t in asyncio.run(m.mcp.list_tools())}
    for name in ("readout_calendar", "snapshot_readouts", "readout_changes_since", "trials_at_risk"):
        sch = getattr(tools[name], "input_schema", None) or tools[name].inputSchema
        assert all(v.get("description") for v in sch["properties"].values()), name
    assert len(tools) == 32


def test_enrich_stamps_any_tool_result():
    r = pv.enrich({"events": [{"key": "a", "url": "https://x", "company": "Viking Therapeutics"}], "errors": []})
    e = r["events"][0]
    assert e["ticker"] == "VKTX" and e["source_url"] == "https://x" and pv.check(e)
    assert pv.enrich([{"nct_id": "NCT1", "lead_sponsor": "Nobody Inc"}])[0]["ticker_confidence"] == 0.0
