"""Offline tests for emawatch (EMA medicines data)."""
from emawatch import core as e

RAW = {"category": "Human", "name_of_medicine": "Foundayo", "ema_product_number": "EMEA/H/C/006400",
       "medicine_status": "Opinion", "opinion_status": "Positive", "latest_procedure_affecting_product_information": "",
       "international_non_proprietary_name_common_name": "Orforglipron", "active_substance": "orforglipron",
       "therapeutic_area_mesh": "Obesity", "atc_code_human": "A10BJ", "therapeutic_indication": "Weight management in adults with obesity",
       "orphan_medicine": "No", "prime_priority_medicine": "No", "conditional_approval": "No", "accelerated_assessment": "No",
       "advanced_therapy": "No", "biosimilar": "No", "generic": "No", "exceptional_circumstances": "No", "additional_monitoring": "Yes",
       "marketing_authorisation_developer_applicant_holder": "Eli Lilly Nederland B.V.", "opinion_adopted_date": "15/10/2026",
       "european_commission_decision_date": "", "marketing_authorisation_date": "", "start_of_evaluation_date": "27/03/2025",
       "last_updated_date": "16/10/2026", "revision_number": "", "medicine_url": "https://www.ema.europa.eu/en/medicines/human/EPAR/foundayo"}
VET = dict(RAW, category="Veterinary", ema_product_number="EMEA/V/C/000001", name_of_medicine="Dogslim")
ORPHAN = dict(RAW, ema_product_number="EMEA/H/C/000002", name_of_medicine="Rarex", international_non_proprietary_name_common_name="rarexumab",
              active_substance="rarexumab", therapeutic_area_mesh="Lymphoma", therapeutic_indication="Relapsed lymphoma",
              orphan_medicine="Yes", medicine_status="Authorised", opinion_status="", opinion_adopted_date="01/02/2024",
              european_commission_decision_date="03/04/2024", marketing_authorisation_date="03/04/2024", start_of_evaluation_date="01/06/2023",
              marketing_authorisation_developer_applicant_holder="Rare Bio GmbH")


class FakeClient:
    def __init__(self, rows): self.rows = rows
    def medicines(self): return self.rows


def test_iso_dates_and_normalize():
    assert e.iso("15/10/2026") == "2026-10-15" and e.iso("1/2/2024") == "2024-02-01"
    assert e.iso("") is None and e.iso(None) is None and e.iso("2026-10-15") is None
    n = e.normalize(RAW)
    assert n["key"] == "EMEA/H/C/006400" and n["inn"] == "Orforglipron" and n["opinion_date"] == "2026-10-15"
    assert n["date"] == "2026-10-15" and n["last_updated"] == "2026-10-16"  # last_updated is not a regulatory event
    assert n["additional_monitoring"] is True and n["orphan_medicine"] is False and n["latest_procedure"] is None
    assert "European Medicines Agency" in n["source"]  # EMA reuse terms require acknowledgement in each copy


def test_search_filters_and_order():
    c = FakeClient([RAW, VET, ORPHAN])
    assert [r["name"] for r in e.search_medicines(c)] == ["Foundayo", "Rarex"]  # human only, newest event first
    assert [r["name"] for r in e.search_medicines(c, category=None)][0] in ("Foundayo", "Dogslim")
    assert [r["name"] for r in e.search_medicines(c, holder="lilly")] == ["Foundayo"]
    assert [r["name"] for r in e.search_medicines(c, drug=["RAREXUMAB"])] == ["Rarex"]
    assert [r["name"] for r in e.search_medicines(c, keyword="obesity")] == ["Foundayo"]
    assert [r["name"] for r in e.search_medicines(c, status=["authorised"])] == ["Rarex"]
    assert [r["name"] for r in e.search_medicines(c, orphan=True)] == ["Rarex"]
    assert [r["name"] for r in e.search_medicines(c, since="2025-01-01")] == ["Foundayo"]
    assert [r["name"] for r in e.search_medicines(c, until="2025-01-01")] == ["Rarex"]
    assert [r["name"] for r in e.search_medicines(c, exclude=["lymphoma"])] == ["Foundayo"]
    assert e.search_medicines(c, max_records=1)[0]["name"] == "Foundayo"


def test_watch_detects_new_medicine_and_ec_decision(tmp_path):
    st = e.store(str(tmp_path / "b.db"))
    assert e.run_watch(FakeClient([RAW]), st, "obesity", keyword="obesity")["baseline"]
    authorised = dict(RAW, medicine_status="Authorised", opinion_status="", european_commission_decision_date="10/12/2026",
                      marketing_authorisation_date="10/12/2026", last_updated_date="11/12/2026")
    other = dict(RAW, ema_product_number="EMEA/H/C/009999", name_of_medicine="Newslim")
    info = e.run_watch(FakeClient([authorised, other]), st, "obesity", keyword="obesity")
    kinds = {(c["key"], c["kind"]) for c in info["changes_detail"]}
    assert ("EMEA/H/C/009999", "new_medicine") in kinds
    assert {("EMEA/H/C/006400", k) for k in ("status_change", "ec_decision_date_change", "authorisation_date_change")} <= kinds
    assert not any(c["kind"] == "last_updated_change" for c in info["changes_detail"])
    again = e.run_watch(FakeClient([authorised, other]), st, "obesity", keyword="obesity")
    assert again["changes"] == 0


def test_umbrella_cli_and_notice():
    import pathlib
    from biocatalystfeed import cli
    assert cli.TOOLS["ema"] == "emawatch.cli" and cli.ALIASES["emawatch"] == "ema" and "ema " in cli.USAGE
    root = pathlib.Path(__file__).resolve().parent.parent
    assert "European Medicines Agency" in (root / "NOTICE").read_text()
