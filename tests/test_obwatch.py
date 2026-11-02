"""obwatch: FDA Orange Book patents/exclusivities (offline, synthetic ZIP)."""
import io, zipfile
import pytest
from obwatch import core as c

PRODUCTS = ("Ingredient~DF;Route~Trade_Name~Applicant~Strength~Appl_Type~Appl_No~Product_No~TE_Code~Approval_Date~RLD~RS~Type~Applicant_Full_Name\r\n"
            "SEMAGLUTIDE~SOLUTION;SUBCUTANEOUS~OZEMPIC~NOVO~2MG/1.5ML~N~209637~001~~Dec 5, 2017~Yes~Yes~RX~NOVO NORDISK INC\r\n"
            "SEMAGLUTIDE~SOLUTION;SUBCUTANEOUS~OZEMPIC~NOVO~4MG/3ML~N~209637~002~~Dec 5, 2017~Yes~Yes~RX~NOVO NORDISK INC\r\n"
            "OLDDRUG~TABLET;ORAL~OLDBRAND~ACME~10MG~N~012345~001~~Approved Prior to Jan 1, 1982~Yes~No~RX~ACME PHARMA INC\r\n"
            "OLDDRUG~TABLET;ORAL~OLDDRUG~GENCO~10MG~A~215328~001~AB~Apr 12, 2023~No~No~RX~GENCO LLC\r\n")
PATENT = ("Appl_Type~Appl_No~Product_No~Patent_No~Patent_Expire_Date_Text~Drug_Substance_Flag~Drug_Product_Flag~Patent_Use_Code~Delist_Flag~Submission_Date\r\n"
          "N~209637~001~8129343~Dec 5, 2031~Y~Y~U-2163~~Jan 2, 2018\r\n"
          "N~209637~002~8129343~Dec 5, 2031~Y~~U-2164~~Jan 2, 2018\r\n"
          "N~209637~001~8129343*PED~Jun 5, 2032~~~~~\r\n"
          "N~012345~001~5000001~Mar 1, 2020~~Y~~~\r\n"
          "N~012345~001~7000002~Jan 15, 2027~~Y~U-1~Y~Feb 1, 2010\r\n")
EXCL = ("Appl_Type~Appl_No~Product_No~Exclusivity_Code~Exclusivity_Date\r\n"
        "N~209637~001~I-935~Mar 8, 2027\r\n"
        "A~215328~001~PC~Dec 1, 2026\r\n")


def zipped(products=PRODUCTS, patent=PATENT, excl=EXCL):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("products.txt", products); z.writestr("patent.txt", patent); z.writestr("exclusivity.txt", excl)
    return b.getvalue()


class Fake:
    def __init__(self, data=None): self.t = c.parse_zip(data or zipped())
    def tables(self): return self.t


T0 = "2026-11-02"


def test_parse_and_merge():
    assert c.iso("Feb 24, 2027") == "2027-02-24" and c.iso("Approved Prior to Jan 1, 1982") is None
    rows = {r["key"]: r for r in c.listings(Fake().tables())}
    p = rows["ob:N209637:patent:8129343"]
    assert p["products"] == ["001", "002"] and p["drug_substance"] and p["drug_product"] and p["use_codes"] == ["U-2163", "U-2164"]
    assert p["expires"] == "2031-12-05" and p["application"] == "NDA 209637" and p["trade_name"] == "OZEMPIC"
    assert p["applicant"] == "NOVO NORDISK INC" and not p["pediatric"] and p["submitted"] == "2018-01-02"
    assert rows["ob:N209637:patent:8129343*PED"]["pediatric"] and rows["ob:N012345:patent:7000002"]["delisted"]
    e = rows["ob:A215328:exclusivity:PC"]
    assert e["application"] == "ANDA 215328" and e["use_codes"] is None and "Appl_Type=A&Appl_No=215328" in e["url"]
    assert p["title"] == "OZEMPIC (NDA 209637) patent 8129343 expires 2031-12-05" and "public domain" in p["source"]


def test_protections_filters():
    f = Fake()
    keys = lambda **kw: [r["key"] for r in c.protections(f, today_=T0, **kw)]
    assert "ob:N012345:patent:5000001" not in keys() and "ob:N012345:patent:5000001" in keys(include_expired=True)
    assert keys(upcoming_days=60) == ["ob:A215328:exclusivity:PC"]
    assert keys(ingredient="semaglutide", kind="exclusivity") == ["ob:N209637:exclusivity:I-935"]
    assert keys(company="novo nordisk", until="2031-12-31") == ["ob:N209637:exclusivity:I-935", "ob:N209637:patent:8129343"]
    assert keys(application="NDA 12345") == ["ob:N012345:patent:7000002"] and keys(application="215328") == ["ob:A215328:exclusivity:PC"]
    assert "ob:N012345:patent:7000002" not in keys(include_delisted=False)
    assert all("OZEMPIC" != r["trade_name"] for r in c.protections(f, today_=T0, exclude=["ozempic"]))
    with pytest.raises(ValueError): c.protections(f, kind="trademark")
    with pytest.raises(ValueError): c.protections(f, application="BLA x")


def test_loe():
    rows = c.loe(Fake(), today_=T0)
    oz = [r for r in rows if r["application"] == "NDA 209637"][0]
    assert oz["last_protection"] == "2032-06-05" and oz["last_protection_code"] == "patent 8129343*PED"
    assert oz["patents"] == 2 and oz["exclusivities"] == 1
    assert [r["application"] for r in rows] == ["ANDA 215328", "NDA 012345", "NDA 209637"]


def test_watch_detects_new_listing_and_expiry_change(tmp_path):
    st = c.store(str(tmp_path / "b.db"))
    assert c.run_watch(Fake(), st, "ob")["baseline"]
    patent2 = PATENT.replace("Dec 5, 2031~Y~Y", "Dec 5, 2033~Y~Y") + "N~209637~001~9999999~Jan 1, 2040~~Y~U-9~~Oct 1, 2026\r\n"
    info = c.run_watch(Fake(zipped(patent=patent2)), st, "ob")
    got = sorted((x["key"], x["kind"], x["new"]) for x in info["changes_detail"])
    assert got == [("ob:N209637:patent:8129343", "expires_change", "2033-12-05"), ("ob:N209637:patent:9999999", "new_listing", None)]


def test_client_cache(tmp_path, monkeypatch):
    calls = []
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr(c.urllib.request, "urlopen", lambda req, timeout=0: calls.append(req.get_header("User-agent")) or R(zipped()))
    cl = c.OrangeBookClient(cache_dir=str(tmp_path))
    assert len(c.listings(cl.tables())) == 6
    c.OrangeBookClient(cache_dir=str(tmp_path)).tables()
    assert len(calls) == 1 and "BioCatalystFeed" in calls[0]
    monkeypatch.setattr(c.urllib.request, "urlopen", lambda req, timeout=0: R(b"<html>blocked</html>"))
    with pytest.raises(RuntimeError): c.OrangeBookClient(cache_dir=str(tmp_path / "x")).fetch()


def test_umbrella_cli_and_mcp():
    from biocatalystfeed import cli
    assert cli.TOOLS["orange-book"] == "obwatch.cli" and cli.ALIASES["ob"] == "orange-book" and "orange-book" in cli.USAGE
    pytest.importorskip("mcp")
    from trialwatch import mcp_server as m
    for n in ("orange_book_protections", "orange_book_loe", "snapshot_orange_book", "orange_book_changes_since"):
        assert callable(getattr(m, n))
