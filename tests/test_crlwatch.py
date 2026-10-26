"""Offline tests for crlwatch (FDA complete response letters from openFDA)."""
import pytest
from crlwatch import core as c

TEXT = """U.S. FOOD & DRUG
ADMINISTRATION

NDA 216586
COMPLETE RESPONSE

Example Therapeutics Inc.
ATTENTION: Jane Doe
Executive Director, Regulatory Affairs

Dear Jane Doe:

Please refer to your May 16, 2023, new drug application (NDA), and your amendments,
submitted under section 505(b) of the Federal Food, Drug, and Cosmetic Act for
rivoceranib tablet.

We have completed our review of this application and have determined that we cannot approve it.

FACILITY INSPECTIONS
1. Following a CGMP inspection of a manufacturing facility listed in this application, FDA
conveyed deficiencies to the representative of the facility.

Reference ID: 5830543

NDA 216586
Page 2

CLINICAL/STATISTICAL
2. The single trial did not meet its primary endpoint.

PRESCRIBING INFORMATION

3. We reserve comment on the proposed labeling until the application is otherwise adequate.

SAFETY UPDATE

When you respond to the above deficiencies, include a safety update.

OTHER
JOHN Q PUBLIC
"""
RAW = {"letter_date": "07/09/2026", "file_name": "CRL_NDA216586_20260709_Redacted.pdf", "letter_year": "2026",
       "approval_status": "Unapproved", "approver_name": "Some Person", "company_rep": "Jane Doe",
       "company_address": "1 Main St", "company_name": "Example Therapeutics Inc.", "text": TEXT,
       "application_number": ["NDA 216586"], "letter_type": "COMPLETE RESPONSE"}
OLD = dict(RAW, letter_date="03/22/2024", file_name="CRL_BLA761303_20240322.pdf", approval_status="Approved",
           company_name="Other Bio", application_number=["BL 761303"],
           text="Please refer to your biologics license application for odronextamab.\n\nPRODUCT QUALITY\n1. Data inadequate.\n")


class Fake:
    def __init__(self, rows): self.rows, self.calls = rows, []
    def query(self, path, search, max_records=500, sort=None):
        self.calls.append((path, search, max_records, sort)); return list(self.rows)[:max_records]


def test_parsers():
    assert c.iso("07/09/2026") == "2026-07-09" and c.iso(None) is None
    assert c.topics_of(TEXT) == ["facility", "clinical"]  # boilerplate headings and signatory names ignored
    assert c.product_of(TEXT) == "rivoceranib tablet"
    ex = c.excerpt_of(TEXT)
    assert ex.startswith("1. Following a CGMP inspection") and "Reference ID" not in ex and "CLINICAL" not in ex
    assert c._topic("SAFETY UPDATE") is None and c._topic("SAFETY") == "safety"
    assert c._topic("CLINICAL PHARMACOLOGY") == "clinical_pharmacology" and c._topic("HUMAN FACTORS") == "human_factors"


def test_normalize_drops_personal_fields():
    n = c.normalize(RAW)
    assert n["key"] == "CRL_NDA216586_20260709_Redacted.pdf" and n["letter_date"] == "2026-07-09"
    assert n["url"] == "https://download.open.fda.gov/crl/CRL_NDA216586_20260709_Redacted.pdf"
    assert n["applications"] == "NDA 216586" and n["application_type"] == "NDA" and n["application_status"] == "Unapproved"
    assert n["title"] == "CRL 2026-07-09 Example Therapeutics Inc. NDA 216586 (rivoceranib tablet)"
    assert "text" not in n and "openFDA" in n["source"]
    flat = repr(n)
    assert "Jane Doe" not in flat and "Some Person" not in flat and "1 Main St" not in flat
    assert c.normalize(OLD)["application_type"] == "BLA"  # 'BL 761303' counts as a BLA
    assert "text" in c.normalize(RAW, include_text=True)


def test_build_search():
    s = c.build_search(since="2026-01-01", company=["Novo Nordisk", "Lilly"], application="NDA 218705", status="Unapproved")
    assert s == ('letter_date:[20260101+TO+29991231]+AND+(company_name:"Novo+Nordisk"+OR+company_name:"Lilly")'
                 '+AND+application_number:*218705*+AND+(approval_status:Unapproved)')
    assert "application_number:*761308*" in c.build_search(application="761308")
    with pytest.raises(ValueError): c.build_search(application="foo")
    with pytest.raises(ValueError): c.build_search(status="Pending")


def test_letters_filters():
    f = Fake([RAW, OLD])
    rows = c.letters(f, max_records=10)
    assert [r["key"] for r in rows] == [RAW["file_name"], OLD["file_name"]] and f.calls[0][0] == "/transparency/crl.json"
    assert f.calls[0][3] == "letter_date:desc" and f.calls[0][2] == 10
    assert [r["key"] for r in c.letters(f, keyword="odronextamab")] == [OLD["file_name"]]
    assert f.calls[-1][2] == 1000  # local filters scan more letters
    assert [r["key"] for r in c.letters(f, topic="facility")] == [RAW["file_name"]]
    assert [r["key"] for r in c.letters(f, exclude=["rivoceranib"])] == [OLD["file_name"]]
    with pytest.raises(ValueError): c.letters(f, topic="pricing")


def test_watch_detects_new_letter_and_approval_flip(tmp_path):
    st = c.store(str(tmp_path / "b.db"))
    assert c.run_watch(Fake([dict(OLD, approval_status="Unapproved")]), st, "crls")["baseline"]
    info = c.run_watch(Fake([RAW, OLD]), st, "crls")
    got = sorted((x["key"], x["kind"], x["new"]) for x in info["changes_detail"])
    assert got == [(OLD["file_name"], "application_status_change", "Approved"), (RAW["file_name"], "new_letter", None)]


def test_umbrella_cli_knows_crl():
    from biocatalystfeed import cli
    assert cli.TOOLS["crl"] == "crlwatch.cli" and cli.ALIASES["crlwatch"] == "crl" and "crl" in cli.USAGE
