"""odwatch: FDA orphan drug designations (offline, synthetic OOPD Excel/HTML table)."""
import io
import pytest
from odwatch import core as c

HEAD = ["Generic Name", "Trade Name", "Date Designated", "Orphan Designation", "Orphan Designation Status",
        "Date Designation Withdrawn or Revoked", "FDA Orphan Approval Status", "Approved Labeled Indication",
        "Marketing Approval Date", "Exclusivity End Date",
        "Exclusivity Protected Indication * (Shown for approvals from Jan. 1, 2013, to the present)", "Sponsor Company",
        "Sponsor Address 1", "Sponsor Address 2", "Sponsor City", "Sponsor State", "Sponsor Zip", "Sponsor Country", "CF Grid Key"]
NA = "Not FDA Approved for Orphan Indication"
ROWS = [
    ["onvansertib", "", "11/09/2026", "treatment of small cell lung cancer", "Designated", "", NA, "", "", "", "",
     "Cardiff Oncology", "11055 Flintkote Avenue", "", "San Diego", "California", "' 92121 '", "United States", "1149626"],
    ["ricefidase", "", "11/19/2026", "treatment of Guillain-Barre syndrome", "Designated", "", NA, "", "", "", "",
     "Shanghai Bao Pharmaceuticals Co., Ltd.", "No. 28, Luoxin Road", "", "Shanghai", "Shanghai", "' 201908 '", "China", "1187926"],
    ["sevabertinib", "Hyrnuo", "03/11/2025", "treatment of NSCLC harboring EGFR or HER2 mutations", "Designated/Approved", "", "",
     "treatment of previously treated HER2-mutant NSCLC", "11/19/2025", "11/19/2032", "previously treated HER2-mutant NSCLC",
     "Bayer HealthCare Pharmaceuticals Inc.", "100 Bayer Blvd", "", "Whippany", "New Jersey", "' 07981 '", "United States", "1036125"],
    ["sevabertinib", "Hyrnuo", "03/11/2025", "treatment of NSCLC harboring EGFR or HER2 mutations", "Designated/Approved", "", "",
     "treatment of first-line HER2-mutant NSCLC", "09/09/2026", "09/09/2033", "first-line HER2-mutant NSCLC",
     "Bayer HealthCare Pharmaceuticals Inc.", "100 Bayer Blvd", "", "Whippany", "New Jersey", "' 07981 '", "United States", "1036125"],
    ["vosoritide", "", "07/11/2025", "treatment of short stature in Turner syndrome", "Designated/Designation Withdrawn or Revoked",
     "04/14/2026", NA, "", "", "", "", "BioMarin Pharmaceutical Inc.", "105 Digital Drive", "", "Novato", "California",
     "' 94949 '", "United States", "1034324"],
    ["voxelotor", "Oxbryta", "01/05/2015", "treatment of sickle cell disease", "Designated/Approved", "", "",
     "treatment of sickle cell disease", "11/25/2019", "11/25/2026", "sickle cell disease in adults",
     "Global Blood Therapeutics, Inc.", "181 Oyster Point", "", "South San Francisco", "California", "' 94080 '", "United States", "455514"],
]


def table(rows=ROWS):
    th = "".join(f"<th>\n {h}\n</th>" for h in HEAD)
    trs = "".join("<tr>" + "".join(f"<td>\n  {x.replace('&', '&amp;')}\n</td>" for x in r) + "</tr>" for r in rows)
    return f"\n <table border=\"1\">\n<tr>{th}</tr>\n{trs}</table>"


class Fake:
    def __init__(self, rows=ROWS): self.r = c.parse_table(table(rows))
    def rows(self): return self.r


T0 = "2026-11-23"


def test_records_merge_and_fields():
    recs = {r["generic_name"]: r for r in c.records(Fake().rows())}
    assert len(recs) == 5
    s = recs["sevabertinib"]
    assert s["key"] == "oopd:1036125" and s["state"] == "approved" and s["trade_names"] == ["Hyrnuo"]
    assert s["approval_dates"] == ["2025-11-19", "2026-09-09"] and s["exclusivity_ends"] == ["2032-11-19", "2033-09-09"]
    assert s["approvals"][0]["date"] == "2026-09-09" and s["latest_approval_date"] == "2026-09-09" and s["date"] == "2026-09-09"
    assert s["url"].endswith("cfgridkey=1036125") and "public domain" in s["source"]
    o = recs["onvansertib"]
    assert o["state"] == "designated" and o["designated_date"] == "2026-11-09" and o["approvals"] == []
    assert o["sponsor"] == "Cardiff Oncology" and o["sponsor_location"] == "San Diego, California, United States"
    assert "Flintkote" not in str(o)  # street addresses are not copied
    assert o["title"] == "onvansertib: FDA orphan designated for treatment of small cell lung cancer (Cardiff Oncology) 2026-11-09"
    v = recs["vosoritide"]
    assert v["state"] == "withdrawn" and v["withdrawn_date"] == "2026-04-14"
    assert [r["generic_name"] for r in c.records(Fake().rows())][:2] == ["ricefidase", "onvansertib"]  # newest event first


def test_designation_filters():
    f = Fake()
    names = lambda **kw: [r["generic_name"] for r in c.designations(f, today_=T0, **kw)]
    assert names(recent_days=30) == ["ricefidase", "onvansertib"]
    assert names(status="designated") == ["ricefidase", "onvansertib"]
    assert names(status=["approved"]) == ["sevabertinib", "voxelotor"] and names(status="withdrawn") == ["vosoritide"]
    assert names(company="cardiff") == ["onvansertib"] and names(product="hyrnuo") == ["sevabertinib"]
    assert names(condition="first-line") == ["sevabertinib"] and names(country="china") == ["ricefidase"]
    assert names(date_by="approved", since="2026-01-01") == ["sevabertinib"]
    assert names(date_by="approved", since="2025-11-01", until="2025-12-01") == ["sevabertinib"]
    assert names(date_by="withdrawn", recent_days=365) == ["vosoritide"]
    assert names(keyword="sickle") == ["voxelotor"] and "ricefidase" not in names(exclude=["shanghai bao*"])
    with pytest.raises(ValueError): c.designations(f, status="pending")
    with pytest.raises(ValueError): c.designations(f, date_by="filed")


def test_exclusivities():
    f = Fake()
    rows = c.exclusivities(f, today_=T0)
    assert [r["exclusivity_end"] for r in rows] == ["2026-11-25", "2032-11-19", "2033-09-09"]
    assert rows[0]["trade_name"] == "Oxbryta" and rows[0]["protected_indication"] == "sickle cell disease in adults"
    assert [r["exclusivity_end"] for r in c.exclusivities(f, upcoming_days=30, today_=T0)] == ["2026-11-25"]
    assert len(c.exclusivities(f, include_expired=True, today_="2040-01-01")) == 3
    assert c.exclusivities(f, company="bayer", today_=T0)[0]["approval_date"] == "2025-11-19"


def test_watch_new_designation_approval_and_transfer(tmp_path):
    st = c.store(str(tmp_path / "b.db"))
    assert c.run_watch(Fake(), st, "od", today_=T0)["baseline"]
    rows2 = [list(r) for r in ROWS]
    rows2[0][4], rows2[0][6], rows2[0][7], rows2[0][8], rows2[0][9] = "Designated/Approved", "", "treatment of SCLC", "11/22/2026", "11/22/2033"
    rows2[1][11] = "New Owner Bio Inc."
    rows2.append(["korro rna editor", "", "11/20/2026", "treatment of urea cycle disorders", "Designated", "", NA, "", "", "", "",
                  "Korro Bio Inc.", "60 First Street", "", "Cambridge", "Massachusetts", "' 02141 '", "United States", "1189226"])
    info = c.run_watch(Fake(rows2), st, "od", today_=T0)
    got = sorted((x["key"], x["kind"]) for x in info["changes_detail"])
    assert ("oopd:1189226", "new_designation") in got and ("oopd:1187926", "sponsor_change") in got
    assert {("oopd:1149626", k) for k in ("status_change", "approved_change", "approval_dates_change", "exclusivity_ends_change")} <= set(got)


def test_client_post_cache_and_block_page(tmp_path, monkeypatch):
    calls = []
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    def fake(req, timeout=0):
        calls.append((req.full_url, req.get_method(), req.get_header("User-agent"), req.data))
        return R(table().encode())
    monkeypatch.setattr(c.urllib.request, "urlopen", fake)
    assert len(c.OOPDClient(cache_dir=str(tmp_path)).rows()) == 6
    c.OOPDClient(cache_dir=str(tmp_path)).rows()
    assert len(calls) == 1 and calls[0][1] == "POST" and "BioCatalystFeed" in calls[0][2] and "Mozilla" not in calls[0][2]
    assert b"Output_Format=Excel" in calls[0][3] and b"Designation_Start_Date=01%2F01%2F1983" in calls[0][3]
    monkeypatch.setattr(c.urllib.request, "urlopen", lambda req, timeout=0: R(b"<html>Access Denied</html>"))
    with pytest.raises(RuntimeError): c.OOPDClient(cache_dir=str(tmp_path / "x")).rows()
    with pytest.raises(RuntimeError): c.parse_table(table().replace("Sponsor Company", "Company"))


def test_umbrella_cli_and_mcp():
    from biocatalystfeed import cli
    assert cli.TOOLS["orphan"] == "odwatch.cli" and cli.ALIASES["oopd"] == "orphan" and "orphan" in cli.USAGE
    from biowatch.watches import TOOLS
    assert TOOLS["oopd"] == ("orphan", "snapshot_orphan_designations", "orphan_changes_since")
    pytest.importorskip("mcp")
    import asyncio
    from trialwatch import mcp_server as m
    d = {t.name: t.description for t in asyncio.run(m.mcp.list_tools())}
    for n in ("orphan_designations", "orphan_exclusivity", "snapshot_orphan_designations", "orphan_changes_since"):
        assert n in d
    assert "baseline" in d["snapshot_orphan_designations"] and "Returns a list" in d["orphan_changes_since"]
