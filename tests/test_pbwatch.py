"""pbwatch: FDA Purple Book licensed biologics / biosimilars / exclusivity (offline, synthetic monthly CSV)."""
import io
import pytest
from pbwatch import core as c

HEAD = ("N/R/U,Applicant,BLA Number,Proprietary Name,Proper Name,License Type,Strength,Dosage Form,Route of Administration,"
        "Product Presentation,Marketing Status,Licensure,Approval Date,Inter. Approval Date,Ref. Product Proper Name,"
        "Ref. Product Proprietary Name,Supplement Number,Submission Type,Inter. Supplement Number,License Number,Product Number,"
        "Center,Date of First Licensure,Exclusivity Expiration Date,First Interchangeable Exclusivity Exp. Date,"
        "Ref. Product Exclusivity Exp. Date,Orphan Exclusivity Exp. Date,Patent List Provided\n")
BLANK = "," * 27 + "\n"
REGN = 'U,"Regeneron Pharmaceuticals, Inc.",125387,Eylea,aflibercept,351(a),2MG/0.05ML,Injection ,Intravitreal,Single-Dose Vial,Rx,Licensed,"November 18, 2011",,,,0,Original,,1760,001,CDER,,,,"May 18, 2024",,YES\n'
AMGN1 = 'U,Amgen Inc.,761298,Pavblu,aflibercept-ayyh,351(k) Biosimilar,2MG/0.05ML,Injection ,Intravitreal,Single-Dose Vial,Rx,Licensed,"August 23, 2024",,aflibercept,Eylea,,Original,,1080,001,CDER,,,,,,\n'
AMGN1_IC = 'U,Amgen Inc.,761298,Pavblu,aflibercept-ayyh,351(k) Interchangeable,2MG/0.05ML,Injection ,Intravitreal,Single-Dose Vial,Rx,Licensed,"August 23, 2024","October 22, 2026",aflibercept,Eylea,,Original,,1080,001,CDER,,,"April 22, 2027",,,\n'
SDZ = 'N,Sandoz Inc.,761382,Enzeevu,aflibercept-abzv,351(k) Biosimilar,2MG/0.05ML,Injection ,Intravitreal,Pre-Filled Syringe,Rx,Licensed,"August 9, 2024",,aflibercept,Eylea,,Original,,2003,001,CDER,,,,,,\n'
GENE = 'N,Ultragenyx Pharmaceutical Inc.,125845,Fayuvi,rebisufligene etisparvovec-hopf,351(a),1.0x10^13VG/ML,Suspension,Intravenous,Single-Dose Vial,Rx,Licensed,"September 17, 2026",,,,0,Original,,2040,001,CDER,"September 17, 2026",,,"September 17, 2038","September 17, 2033",\n'
OLD1 = ',EMD Serono Inc.,020378,Gonal-f,follitropin alfa,351(a),75IU,For Injection,Subcutaneous,Multi-Dose Vial,Rx,Licensed,"September 29, 1997",,,,0,Original,,1773,001,CDER,,,,,,\n'
OLD2 = ',EMD Serono Inc.,020378,Gonal-f,follitropin alfa,351(a),450IU,For Injection,Subcutaneous,Multi-Dose Vial,Disc,Voluntarily Revoked,"February 28, 2001",,,,9,Supplement,,1773,002,CDER,,,,,,\n'
GONE = ',Acme Bio,103000,Oldmab,oldmab,351(a),10MG,Injection ,Intravenous,Vial,Disc,Revoked,"March 1, 1999",,,,0,Original,,0999,001,CBER,,,,,,\n'


def csv_text(month="October 2026", changes=(GENE, SDZ), full=(REGN, AMGN1, SDZ, GENE, OLD1, OLD2, GONE), bom=True):
    s = ("\ufeff" if bom else "") + f"Purple Book Monthly Historical Data Changes Report - {month}" + "," * 27 + "\n" + BLANK
    s += "Newly Approved Products (N)  / Products Added in Current Release (R) / Updated Products (U)" + "," * 27 + "\n" + HEAD
    s += "".join(changes) + BLANK + HEAD + "".join("," + r.split(",", 1)[1] for r in full)
    return s


class Fake:
    def __init__(self, text=None): self.t = c.parse_csv(text or csv_text())
    def tables(self): return self.t


T0 = "2026-11-16"


def test_parse_and_merge():
    t = c.parse_csv(csv_text())
    assert t["report"] == "October 2026" and len(t["changes"]) == 2 and len(t["products"]) == 7
    assert c.iso("October 22, 2026") == "2026-10-22" and c.iso("Not Eligible") is None
    rows = {r["key"]: r for r in c.licenses(t)}
    assert len(rows) == 6 and list(rows)[0] == "pb:125845"  # newest approval first
    g = rows["pb:020378"]
    assert g["licensure"] == "Licensed" and g["products"] == ["001"] and g["revoked_products"] == 1 and g["marketing_status"] == ["Rx"]
    e = rows["pb:125387"]
    assert e["ref_exclusivity_expires"] == "2024-05-18" and e["patent_list_provided"] and not e["biosimilar"] and e["pathway"] == "351(a)"
    p = rows["pb:761298"]
    assert p["biosimilar"] and not p["interchangeable"] and p["reference_product"] == "Eylea" and p["reference_proper_name"] == "aflibercept"
    assert p["bla"] == "BLA 761298" and "blaNo=761298" in p["url"] and "public domain" in p["source"]
    assert rows["pb:125845"]["monthly_flags"] == ["N"] and rows["pb:125845"]["orphan_exclusivity_expires"] == "2033-09-17"
    assert rows["pb:103000"]["licensure"] == "Revoked" and rows["pb:103000"]["products"] == []
    assert p["title"] == "Pavblu (aflibercept-ayyh, BLA 761298) biosimilar to Eylea, Amgen Inc., approved 2024-08-23"
    with pytest.raises(RuntimeError): c.parse_csv("<html>Sorry! This resembles an automated request.</html>")
    with pytest.raises(RuntimeError): c.parse_csv(csv_text().replace("Ref. Product Exclusivity Exp. Date", "Something Else"))


def test_products_filters():
    f = Fake()
    keys = lambda **kw: [r["key"] for r in c.products(f, today_=T0, **kw)]
    assert "pb:103000" not in keys() and "pb:103000" in keys(include_revoked=True)
    assert keys(license_type="biosimilar") == ["pb:761298", "pb:761382"]
    assert keys(license_type="351(a)", center="cder") == ["pb:125845", "pb:125387", "pb:020378"]
    assert keys(reference="eylea") == ["pb:761298", "pb:761382"] and keys(company="sandoz") == ["pb:761382"]
    assert keys(recent_days=90) == ["pb:125845"] and keys(since="2024-08-01", until="2024-08-31") == ["pb:761298", "pb:761382"]
    assert keys(monthly_changes=True) == ["pb:125845", "pb:761382"] and keys(application="BLA 20378") == ["pb:020378"]
    assert keys(name="eylea") == ["pb:125387"] and keys(name="aflibercept") == ["pb:761298", "pb:761382", "pb:125387"]
    assert "pb:761382" not in keys(exclude=["sandoz"])
    with pytest.raises(ValueError): c.products(f, license_type="generic")
    with pytest.raises(ValueError): c.products(f, application="NDA 1")


def test_exclusivities():
    f = Fake()
    rows = c.exclusivities(f, today_=T0)
    assert [(r["bla"], r["kind"], r["expires"]) for r in rows] == [("BLA 125845", "orphan", "2033-09-17"), ("BLA 125845", "reference", "2038-09-17")]
    assert [r["kind"] for r in c.exclusivities(f, today_=T0, include_expired=True)][0] == "reference"  # Eylea 2024
    assert c.exclusivities(f, today_=T0, upcoming_days=365) == []
    assert c.exclusivities(f, today_=T0, kind="orphan")[0]["title"] == "Fayuvi (BLA 125845) orphan exclusivity expires 2033-09-17"
    with pytest.raises(ValueError): c.exclusivities(f, kind="patent")


def test_landscape():
    f = Fake()
    rows = c.landscape(f, today_=T0)
    assert len(rows) == 1
    a = rows[0]
    assert a["reference_product"] == "Eylea" and a["reference_blas"] == ["BLA 125387"] and a["biosimilars"] == 2
    assert a["interchangeables"] == 0 and a["reference_exclusivity_expires"] == "2024-05-18" and a["reference_exclusivity_expired"]
    assert [p["name"] for p in a["products"]] == ["Enzeevu", "Pavblu"] and a["first_biosimilar_approved"] == "2024-08-09"
    un = c.landscape(f, today_=T0, include_unchallenged=True)
    assert [r["reference_product"] for r in un] == ["Eylea", "Fayuvi"] and un[1]["biosimilars"] == 0 and un[1]["key"] == "pbl:rebisufligene etisparvovec:125845"
    assert c.landscape(f, today_=T0, reference="stelara") == [] and len(c.landscape(f, today_=T0, company="sandoz")) == 1
    assert c._core("adalimumab-aaty") == "adalimumab"


def test_watch_detects_new_bla_interchangeable_and_revocation(tmp_path):
    st = c.store(str(tmp_path / "b.db"))
    assert c.run_watch(Fake(), st, "pb")["baseline"]
    new = 'N,Biocon Biologics Inc.,761274,Yesafili,aflibercept-jbvf,351(k) Biosimilar,2MG/0.05ML,Injection ,Intravitreal,Single-Dose Vial,Rx,Licensed,"May 20, 2024",,aflibercept,Eylea,,Original,,2324,001,CDER,,,,,,\n'
    old1_revoked = OLD1.replace(",Rx,Licensed,", ",Disc,Voluntarily Revoked,")
    info = c.run_watch(Fake(csv_text(month="November 2026", full=(REGN, AMGN1_IC, SDZ, GENE, old1_revoked, OLD2, GONE, new))), st, "pb")
    got = sorted((x["key"], x["kind"], x["new"]) for x in info["changes_detail"])
    assert ("pb:761274", "new_bla", None) in got
    assert ("pb:761298", "interchangeable_approved_change", "2026-10-22") in got
    assert ("pb:761298", "interchangeable_exclusivity_expires_change", "2027-04-22") in got
    assert ("pb:761298", "license_types_change", "['351(k) Interchangeable']") in got
    assert ("pb:020378", "licensure_change", "Voluntarily Revoked") in got
    assert all(k[0] in ("pb:761274", "pb:761298", "pb:020378") for k in got)


def test_latest_link_and_discover():
    html = ('<a href="https://www.accessdata.fda.gov/drugsatfda_docs/PurpleBook/2025/purplebook-search-december-data-download.csv">'
            '<a href="https://www.accessdata.fda.gov/drugsatfda_docs/PurpleBook/2026/purplebook-search-january-data-download.csv">'
            '<a href="https://www.accessdata.fda.gov/drugsatfda_docs/PurpleBook/2026/purplebook-search-October-data-download.csv">'
            '<a href="https://www.accessdata.fda.gov/drugsatfda_docs/PurpleBook/2026/purplebook-search-October-data-download.xlsx">'
            '<a href="https://www.accessdata.fda.gov/drugsatfda_docs/PurpleBook/2026/purplebook-search-March-data-download.csv">')
    assert c.latest_link(html) == ("https://www.accessdata.fda.gov/drugsatfda_docs/PurpleBook/2026/purplebook-search-October-data-download.csv", "October 2026")
    assert c.latest_link("<html>nothing</html>") is None


class R(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass


def test_client_discovers_caches_and_rejects(tmp_path, monkeypatch):
    link = "https://www.accessdata.fda.gov/drugsatfda_docs/PurpleBook/2026/purplebook-search-October-data-download.csv"
    calls = []

    def fake(req, timeout=0):
        calls.append((req.full_url, req.get_header("User-agent")))
        return R(f'<a href="{link}">CSV</a>'.encode() if "event=downloads" in req.full_url else csv_text().encode("utf-8"))
    monkeypatch.setattr(c.urllib.request, "urlopen", fake)
    cl = c.PurpleBookClient(cache_dir=str(tmp_path))
    t = cl.tables()
    assert t["report"] == "October 2026" and t["url"] == link and len(c.licenses(t)) == 6
    assert [u for u, _ in calls] == [c.DOWNLOADS, link] and all("BioCatalystFeed" in ua for _, ua in calls)
    assert c.PurpleBookClient(cache_dir=str(tmp_path)).tables()["url"] == link and len(calls) == 2  # cached
    monkeypatch.setattr(c.urllib.request, "urlopen", lambda req, timeout=0: R(b"<html>Sorry! This resembles an automated request.</html>"))
    with pytest.raises(RuntimeError): c.PurpleBookClient(cache_dir=str(tmp_path / "x")).fetch()


def test_client_falls_back_and_retries_once(tmp_path, monkeypatch):
    seen = []

    def fake(req, timeout=0):
        u = req.full_url; seen.append(u)
        if "event=downloads" in u: raise c.urllib.error.HTTPError(u, 401, "challenge", {}, None)
        if seen.count(u) == 1: raise c.urllib.error.HTTPError(u, 401, "edge", {}, None)  # transient: retried once
        return R(csv_text(bom=False).encode("utf-8"))
    monkeypatch.setattr(c.urllib.request, "urlopen", fake)
    cl = c.PurpleBookClient(cache_dir=str(tmp_path)); cl.retry_pause = 0
    data, url = cl.fetch()
    assert c.looks_like_purple_book(data) and url.endswith("-data-download.csv") and "/PurpleBook/" in url
    assert seen[:2] == [c.DOWNLOADS] * 2 and seen[2] == seen[3] == url


def test_umbrella_cli_and_mcp():
    from biocatalystfeed import cli
    assert cli.TOOLS["purple-book"] == "pbwatch.cli" and cli.ALIASES["pb"] == "purple-book" and "purple-book" in cli.USAGE
    from biowatch.watches import TOOLS
    assert TOOLS["pb"][0] == "purple-book"
    pytest.importorskip("mcp")
    from trialwatch import mcp_server as m
    for n in ("purple_book_products", "purple_book_exclusivity", "purple_book_biosimilar_landscape",
              "snapshot_purple_book", "purple_book_changes_since"):
        assert callable(getattr(m, n))
