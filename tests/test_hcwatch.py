"""hcwatch: Health Canada Notices of Compliance (offline, synthetic tables)."""
import io, json
import pytest
from hcwatch import core as c

MAIN = [
    {"noc_number": 38583, "noc_date": "2026-11-04", "noc_manufacturer_name": "MODERNA BIOPHARMA CANADA CORPORATION",
     "noc_status_with_conditions": "N", "noc_on_submission_type": "New Drug Submission", "noc_is_suppliment": "N",
     "noc_submission_class": "New Active Substance", "noc_is_admin": "N", "noc_product_type": "Biologic",
     "noc_crp_product_name": "", "noc_crp_company_name": "", "noc_crp_country_name": "", "noc_active_status": "1",
     "noc_reason_supplement": "", "noc_reason_submission": "", "noc_therapeutic_class": "", "noc_last_update_date": "1111-11-11"},
    {"noc_number": 38500, "noc_date": "2026-09-24", "noc_manufacturer_name": "BOEHRINGER INGELHEIM (CANADA) LTD LTEE",
     "noc_status_with_conditions": "Y", "noc_on_submission_type": "New Drug Submission", "noc_is_suppliment": "N",
     "noc_submission_class": "Priority-NAS", "noc_is_admin": "N", "noc_product_type": "Prescription Pharmaceutical",
     "noc_active_status": "1", "noc_reason_supplement": "", "noc_reason_submission": "", "noc_therapeutic_class": ""},
    {"noc_number": 38590, "noc_date": "2026-11-05", "noc_manufacturer_name": "STERINOVA INC", "noc_status_with_conditions": "N",
     "noc_on_submission_type": "Supplement to an Abb", "noc_is_suppliment": "Y", "noc_submission_class": "Other",
     "noc_is_admin": "N", "noc_product_type": "Prescription Pharmaceutical", "noc_crp_product_name": "HYDROMORPHONE INJECTION",
     "noc_crp_company_name": "PFIZER CANADA ULC", "noc_crp_country_name": "CANADA", "noc_active_status": "1",
     "noc_reason_supplement": "Update to package labels\nNew strength", "noc_reason_submission": ""},
    {"noc_number": 38548, "noc_date": "2026-10-29", "noc_manufacturer_name": "XEDITON PHARMACEUTICALS INC",
     "noc_on_submission_type": "New Drug Submission", "noc_is_suppliment": "N", "noc_submission_class": "Admin",
     "noc_is_admin": "N", "noc_product_type": "Prescription Pharmaceutical", "noc_active_status": "1",
     "noc_reason_submission": "Administrative: Change in product ownership"},
    {"noc_number": 30000, "noc_date": "2020-01-01", "noc_manufacturer_name": "VETCO", "noc_on_submission_type": "New Drug Submission",
     "noc_submission_class": "Other", "noc_product_type": "Veterinary", "noc_active_status": "1"},
]
PRODUCTS = [{"noc_number": 38583, "noc_br_brandname": "MCOFLU", "noc_br_din": "02555555"},
            {"noc_number": 38583, "noc_br_brandname": "MCOFLU", "noc_br_din": "02555556"},
            {"noc_number": 38500, "noc_br_brandname": "HERNEXEOS", "noc_br_din": "02544444"}]
INGR = [{"noc_number": 38583, "noc_pi_medic_ingr_name": "MRNA-1010"}, {"noc_number": 38500, "noc_pi_medic_ingr_name": "ZONGERTINIB"},
        {"noc_number": 38590, "noc_pi_medic_ingr_name": "HYDROMORPHONE HYDROCHLORIDE"}]


class Fake:
    def __init__(self, main=MAIN): self.t = {"noticeofcompliancemain": main, "drugproduct": PRODUCTS, "medicinalingredient": INGR}
    def tables(self): return self.t


T0 = "2026-11-09"


def test_records_join_and_flags():
    rows = {r["noc_number"]: r for r in c.records(Fake().tables())}
    m = rows[38583]
    assert m["brand_names"] == ["MCOFLU"] and m["dins"] == ["02555555", "02555556"] and m["ingredients"] == ["MRNA-1010"]
    assert m["submission"] == "NDS" and m["new_active_substance"] and not m["priority"] and not m["with_conditions"]
    assert m["url"].endswith("no=38583") and "Open Government Licence" in m["source"]
    assert m["title"] == "MCOFLU (MODERNA BIOPHARMA CANADA CORPORATION) Health Canada NDS NAS 2026-11-04"
    h = rows[38500]
    assert h["priority"] and h["with_conditions"] and "NOC/c" in h["title"]
    s = rows[38590]
    assert s["submission"] == "SANDS" and s["supplement"] and s["reason"] == "Update to package labels; New strength"
    assert s["reference_product"] == "HYDROMORPHONE INJECTION / PFIZER CANADA ULC / CANADA"
    assert rows[38548]["administrative"]
    assert [r["noc_number"] for r in c.records(Fake().tables())][:2] == [38590, 38583]  # newest first


def test_notices_filters():
    f = Fake()
    nums = lambda **kw: [r["noc_number"] for r in c.notices(f, today_=T0, **kw)]
    assert nums() == [38590, 38583, 38500]  # admin + veterinary dropped by default
    assert 38548 in nums(include_admin=True) and 30000 in nums(include_veterinary=True)
    assert nums(new_active_substance=True) == [38583, 38500] and nums(with_conditions=True) == [38500]
    assert nums(priority=True) == [38500] and nums(submission=["sands"]) == [38590]
    assert nums(company="moderna") == [38583] and nums(ingredient="zongertinib") == [38500] and nums(brand="mcoflu") == [38583]
    assert nums(recent_days=30) == [38590, 38583] and nums(since="2026-11-05") == [38590] and nums(until="2026-10-01") == [38500]
    assert nums(keyword="strength") == [38590] and nums(exclude=["hydromorphone"]) == [38583, 38500]
    with pytest.raises(ValueError): c.notices(f, submission="BLA")


def test_watch_new_noc_and_suspension(tmp_path):
    st = c.store(str(tmp_path / "b.db"))
    assert c.run_watch(Fake(), st, "hc", today_=T0)["baseline"]
    main2 = [dict(r) for r in MAIN]
    main2[1]["noc_active_status"] = "0"
    main2.append(dict(MAIN[0], noc_number=38600, noc_date="2026-11-08"))
    info = c.run_watch(Fake(main2), st, "hc", today_=T0)
    got = sorted((x["key"], x["kind"]) for x in info["changes_detail"])
    assert got == [("hcnoc:38500", "active_change"), ("hcnoc:38600", "new_noc")]


def test_client_cache(tmp_path, monkeypatch):
    calls = []
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    data = {"noticeofcompliancemain": MAIN, "drugproduct": PRODUCTS, "medicinalingredient": INGR}
    def fake(req, timeout=0):
        calls.append((req.full_url, req.get_header("User-agent")))
        return R(json.dumps([t for k, t in data.items() if f"/{k}/" in req.full_url][0]).encode())
    monkeypatch.setattr(c.urllib.request, "urlopen", fake)
    assert len(c.records(c.NOCClient(cache_dir=str(tmp_path)).tables())) == 5
    c.NOCClient(cache_dir=str(tmp_path)).tables()
    assert len(calls) == 3 and all("BioCatalystFeed" in ua for _, ua in calls)
    monkeypatch.setattr(c.urllib.request, "urlopen", lambda req, timeout=0: R(b"<html>blocked</html>"))
    with pytest.raises(RuntimeError): c.NOCClient(cache_dir=str(tmp_path / "x")).fetch("drugproduct")


def test_umbrella_cli_and_mcp():
    from biocatalystfeed import cli
    assert cli.TOOLS["health-canada"] == "hcwatch.cli" and cli.ALIASES["hc"] == "health-canada" and "health-canada" in cli.USAGE
    pytest.importorskip("mcp")
    import asyncio
    from trialwatch import mcp_server as m
    d = {t.name: t.description for t in asyncio.run(m.mcp.list_tools())}
    for n in ("health_canada_notices", "snapshot_health_canada", "health_canada_changes_since"):
        assert n in d
    assert "baseline" in d["snapshot_health_canada"] and "Returns a list" in d["health_canada_changes_since"]
