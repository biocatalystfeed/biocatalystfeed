"""Offline tests for decisionwatch (FDA decision calendar + watch)."""
import json
import pytest
from decisionwatch import core as d

TODAY = "2026-10-28"
PR = ("Acme Bio announced that the FDA accepted its NDA for zorbitinib for obesity. The Prescription Drug User Fee Act "
      "(PDUFA) target action date is March 14, 2027. Other text.")


class FakeSEC:
    def __init__(self, text=PR): self.text_ = text; self.q = []
    def fts(self, q, ciks=None, forms="8-K", since=None, until=None, max_hits=100):
        self.q.append((q, ciks))
        return [{"_id": "0000000000-26-000001:ex99.htm", "_source": {"ciks": ["0001234567"], "adsh": "0000000000-26-000001",
                 "display_names": ["Acme Bio, Inc.  (ACME)  (CIK 0001234567)"], "file_date": "2026-10-01", "form": "8-K"}}]
    def text(self, url): return self.text_
    def ticker_cik(self, t): return "1234567"
    def get_json(self, url): return {"0": {"ticker": "ACME", "title": "Acme Bio, Inc.", "cik_str": 1234567}}


class FakeFR:
    def documents(self, since=None, until=None, max_pages=5):
        return [{"document_number": "2026-1", "title": "Endocrinologic and Metabolic Drugs Advisory Committee; Notice of Meeting",
                 "abstract": "notice of meeting", "dates": "The meeting will be held on December 3, 2026.",
                 "publication_date": "2026-10-10", "html_url": "https://www.federalregister.gov/d/2026-1"}]
    def full_text(self, url): return ""


class FakeFDA:
    def __init__(self, crl=()): self.crl = list(crl)
    def query(self, path, search, max_records=500, sort=None): return self.crl
    def drugsfda(self, **kw):
        return [{"application_number": "NDA999999", "sponsor_name": "ACME",
                 "products": [{"brand_name": "ZORBA", "active_ingredients": [{"name": "ZORBITINIB"}]}],
                 "openfda": {"pharm_class_epc": ["Kinase Inhibitor [EPC]"]},
                 "submissions": [{"submission_type": "ORIG", "submission_number": "1", "submission_status": "AP",
                                  "submission_status_date": "20261020", "review_priority": "PRIORITY"}]}]


def test_parse_when():
    assert d.parse_when("March 14, 2027") == ("2027-03-14", "day")
    assert d.parse_when("March 2027") == ("2027-03-01", "month")
    assert d.parse_when("second quarter of 2027") == ("2027-04-01", "quarter")
    assert d.parse_when("Q3 2027") == ("2027-07-01", "quarter")
    assert d.parse_when("first half 2027") == ("2027-01-01", "half")
    assert d.parse_when("3/14/2027") == ("2027-03-14", "day")
    assert d.parse_when("nonsense") == (None, None)


def test_pdufa_event_has_provenance_and_confidence():
    ev = d.pdufa_events(FakeSEC(), today=TODAY)
    assert len(ev) == 1
    e = ev[0]
    assert e["kind"] == "pdufa" and e["date"] == "2027-03-14" and e["confidence"] == "company-disclosed"
    assert e["ticker"] == "ACME" and e["drug"] == "zorbitinib" and e["status"] == "pending"
    assert e["url"].startswith("https://www.sec.gov/Archives/") and "UNVERIFIED" in e["provenance"]["method"]


def test_drug_and_condition_filters_go_to_fts():
    s = FakeSEC()
    assert d.pdufa_events(s, drug="zorbitinib", condition="obesity", today=TODAY)
    assert '"zorbitinib"' in s.q[0][0] and '"obesity"' in s.q[0][0]
    assert d.pdufa_events(FakeSEC(), drug="otherdrug", today=TODAY) == []


def test_merged_calendar_order_and_upcoming():
    evs = d.decisions(FakeFDA(), FakeFR(), FakeSEC(), today=TODAY)
    kinds = [e["kind"] for e in evs]
    assert kinds[:2] == ["adcom", "pdufa"]  # upcoming soonest first: 2026-12-03 then 2027-03-14
    assert "approval" in kinds
    up = d.decisions(FakeFDA(), FakeFR(), FakeSEC(), upcoming_days=60, today=TODAY)
    assert [e["kind"] for e in up] == ["adcom"]


def test_bad_kind_and_source_error_isolated():
    with pytest.raises(ValueError): d.decisions(kinds=["nope"], today=TODAY)
    class Boom(FakeSEC):
        def fts(self, *a, **k): raise RuntimeError("down")
    errs = []
    evs = d.decisions(FakeFDA(), FakeFR(), Boom(), errors=errs, today=TODAY)
    assert errs and errs[0]["kind"] == "pdufa" and evs


def test_ticker_resolution_via_sec_list():
    al = d.resolve_company("ACME", FakeSEC())
    assert al["ticker"] == "ACME" and al["sec_cik"] == "1234567" and al["canonical"] == "Acme Bio, Inc."


def test_watch_detects_pdufa_date_change(tmp_path):
    st = d.store(str(tmp_path / "w.db"))
    a = d.run_watch(FakeFDA(), FakeFR(), FakeSEC(), st, "w", kinds=["pdufa"], today=TODAY)
    assert a["baseline"] and a["changes"] == 0
    b = d.run_watch(FakeFDA(), FakeFR(), FakeSEC(PR.replace("March 14, 2027", "June 14, 2027")), st, "w", kinds=["pdufa"], today=TODAY)
    ch = b["changes_detail"]
    assert [(c["kind"], c["old"], c["new"]) for c in ch] == [("date_change", "2027-03-14", "2027-06-14")]
    assert st.changes(watch="w")[0]["field"] == "date"


def test_mcp_tools_registered_with_descriptions():
    import asyncio
    from trialwatch import mcp_server as m
    tools = {t.name: t for t in asyncio.run(m.mcp.list_tools())}
    for n in ("fda_decisions", "snapshot_fda_decisions", "fda_decision_changes_since"):
        assert n in tools
        t = tools[n]; props = (getattr(t, "input_schema", None) or t.inputSchema)["properties"]
        assert all(p.get("description") for p in props.values()), n
