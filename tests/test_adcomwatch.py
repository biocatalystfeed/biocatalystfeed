"""Offline tests for adcomwatch (FDA advisory committee notices from the Federal Register API)."""
from adcomwatch import core as a

ODAC = {"title": "Oncologic Drugs Advisory Committee; Notice of Meeting; Establishment of a Public Docket; Request for Comments",
        "document_number": "2026-04497", "publication_date": "2026-03-09",
        "dates": "The meeting will be held on April 30, 2026, from 8:00 a.m. to 5:00 p.m. Eastern Time.",
        "html_url": "https://www.federalregister.gov/documents/2026/03/09/2026-04497/x", "raw_text_url": "https://fr.test/odac.txt",
        "docket_ids": ["Docket No. FDA-2026-N-1867"], "abstract": "FDA announces a forthcoming public advisory committee meeting."}
ODAC_TEXT = """<html><body><pre>
DATES: The meeting will be held on April 30, 2026.

SUPPLEMENTARY INFORMATION: 
    Agenda: The meeting presentations will be heard, viewed, captioned, 
and recorded through an online teleconferencing and/or video 
conferencing platform. On the morning of April 30, 2026, the Committee 
will discuss new drug application (NDA) 220359, for camizestrant 
tablets, submitted by AstraZeneca Pharmaceuticals LP. On the 
afternoon the Committee will discuss supplemental 
new drug application (sNDA) 218197/S-004, for Truqap (capivasertib) 
tablets, submitted by AstraZeneca Pharmaceuticals LP. The proposed indication is prostate cancer.
    FDA intends to make background materials available to the public.
</pre></body></html>"""
AMEND = {"title": "Cellular, Tissue, and Gene Therapies Advisory Committee; Notice of Meeting; Establishment of a Public Docket; "
                  "Request for Comments-Biologics License Application (BLA) 125827, From Replimune, Inc. for Vusolimogene Oderparepvec",
         "document_number": "2026-15017", "publication_date": "2026-07-24", "dates": None, "html_url": "https://fr.test/amend",
         "raw_text_url": "https://fr.test/amend.txt", "abstract": "FDA is announcing an amendment to the notice of meeting of the Committee."}
AMEND_TEXT = "SUPPLEMENTARY INFORMATION: FDA announced that a meeting would be held on July 30, 2026. The DATES portion is changed."
TOBACCO = dict(ODAC, title="Tobacco Products Scientific Advisory Committee; Notice of Meeting", document_number="2026-1")
NOMINATION = dict(ODAC, title="Request for Nominations for Voting Members on a Public Advisory Committee; Tobacco Products", document_number="2026-2")
DEVICES = dict(ODAC, title="Microbiology Devices Panel of the Medical Devices Advisory Committee; Notice of Meeting",
               document_number="2026-18920", publication_date="2026-09-16",
               dates="The meeting will be held on November 19, 2026, from 9 a.m. to 4 p.m.", raw_text_url="https://fr.test/dev.txt")
CANCEL = dict(ODAC, title="Pediatric Advisory Committee; Cancellation of Meeting", document_number="2026-3", dates=None)


class Fake:
    def __init__(self, docs, texts=None): self.docs, self.texts, self.fetched = docs, texts or {}, []
    def documents(self, since=None, until=None, max_pages=5): return list(self.docs)
    def full_text(self, url): self.fetched.append(url); return self.texts.get(url, "")


def test_parsers():
    assert a.iso_dates("held on July 23, 2026 and July 24, 2026; also February 30, 2026") == ["2026-07-23", "2026-07-24"]
    assert a.kind_of(ODAC["title"]) == "meeting" and a.kind_of(NOMINATION["title"]) is None
    assert a.kind_of(CANCEL["title"]) == "cancellation" and a.kind_of(AMEND["title"], AMEND["abstract"]) == "amendment"
    assert [a.area_of(x) for x in ("Oncologic Drugs Advisory Committee", "Vaccines and Related Biological Products Advisory Committee",
                                   "Microbiology Devices Panel of the Medical Devices Advisory Committee",
                                   "Tobacco Products Scientific Advisory Committee", "Pediatric Advisory Committee")] == \
        ["drugs", "biologics", "devices", "tobacco", "other"]
    ag = a.agenda_of(ODAC_TEXT)
    assert ag.startswith("On the morning of April 30, 2026") and "heard, viewed" not in ag and "background" not in ag
    assert a.dates_of(AMEND_TEXT) == "would be held on July 30, 2026"


def test_normalize_extracts_applications_and_sponsors():
    n = a.normalize(ODAC, a.agenda_of(ODAC_TEXT))
    assert n["key"] == "2026-04497" and n["committee"] == "Oncologic Drugs Advisory Committee" and n["area"] == "drugs"
    assert n["meeting_date"] == "2026-04-30" and n["kind"] == "meeting" and n["docket"] == "Docket No. FDA-2026-N-1867"
    assert n["applications"] == "NDA 220359, sNDA 218197/S-004" and n["sponsors"] == "AstraZeneca Pharmaceuticals LP"
    assert "Federal Register" in n["source"]
    m = a.normalize(AMEND)  # application + sponsor from the title alone
    assert m["applications"] == "BLA 125827" and m["sponsors"] == "Replimune, Inc." and m["meeting_date"] is None


def test_meetings_filters_and_agenda_fetch():
    c = Fake([ODAC, AMEND, TOBACCO, NOMINATION, DEVICES, CANCEL], {"https://fr.test/odac.txt": ODAC_TEXT, "https://fr.test/amend.txt": AMEND_TEXT})
    rows = a.meetings(c, today="2026-10-21")
    assert [r["key"] for r in rows] == ["2026-18920", "2026-15017", "2026-04497", "2026-3"]  # newest meeting first; no tobacco/nominations
    assert rows[1]["meeting_date"] == "2026-07-30"  # amendment: date recovered from full text
    assert "https://fr.test/odac.txt" in c.fetched and len(c.fetched) == 3  # cancellations aren't fetched
    assert [r["key"] for r in a.meetings(c, upcoming=True, today="2026-10-21")] == ["2026-18920"]
    assert [r["key"] for r in a.meetings(c, area=["drugs"], today="2026-10-21")] == ["2026-04497"]
    assert [r["key"] for r in a.meetings(c, area="tobacco", today="2026-10-21")] == ["2026-1"]
    assert [r["key"] for r in a.meetings(c, keyword="camizestrant", today="2026-10-21")] == ["2026-04497"]
    assert [r["key"] for r in a.meetings(c, committee="cellular", today="2026-10-21")] == ["2026-15017"]
    assert all(r["key"] != "2026-18920" for r in a.meetings(c, exclude=["microbiology"], today="2026-10-21"))
    c2 = Fake([ODAC]); assert a.meetings(c2, agenda=False)[0]["applications"] is None and c2.fetched == []


def test_watch_detects_new_notice(tmp_path):
    st = a.store(str(tmp_path / "b.db"))
    assert a.run_watch(Fake([ODAC]), st, "adcoms", today="2026-10-21")["baseline"]
    info = a.run_watch(Fake([ODAC, DEVICES]), st, "adcoms", today="2026-10-21")
    assert [(c["key"], c["kind"]) for c in info["changes_detail"]] == [("2026-18920", "new_notice")]


def test_umbrella_cli_knows_adcom():
    from biocatalystfeed import cli
    assert cli.TOOLS["adcom"] == "adcomwatch.cli" and cli.ALIASES["adcomwatch"] == "adcom" and "adcom" in cli.USAGE
