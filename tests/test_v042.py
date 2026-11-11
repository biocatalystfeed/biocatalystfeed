"""0.4.2: iCalendar export, static per-company / per-month calendar pages + sitemap, list_watches MCP tool."""
import json, os, sqlite3, subprocess, sys
from datetime import datetime, timezone
from biowatch import ics
from biowatch.store import ItemStore
from biowatch.watches import list_watches
from readoutwatch import core as rc, page
from tests.test_readoutwatch import FakeCT, study, TODAY

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def _unfold(text):
    return text.replace("\r\n ", "")


def test_ics_readouts_valid_and_stable():
    rows = rc.readouts(FakeCT([study("NCT00000002", "2026-12-01"), study("NCT00000003", "2027-01", typ="ACTUAL")]), today=TODAY)
    a = ics.calendar("Readouts, test; x", rows, now=NOW)
    b = ics.calendar("Readouts, test; x", rows, now=NOW)
    assert a == b and a.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n") and a.endswith("END:VCALENDAR\r\n")
    assert all(len(l.encode()) <= 75 for l in a.split("\r\n")), "lines folded at 75 octets"
    u = _unfold(a)
    assert u.count("BEGIN:VEVENT") == 2 and "DTSTART;VALUE=DATE:20261201" in u and "DTEND;VALUE=DATE:20261202" in u
    assert "DTSTART;VALUE=DATE:20270101" in u and "Date precision: month" in u
    assert "X-WR-CALNAME:Readouts\\, test\\; x" in u
    assert "VKTX P3 readout (est.)" in u and "URL:https://clinicaltrials.gov/study/NCT00000002" in u
    assert "Not investment" in u and "DTSTAMP:20261111T120000Z" in u
    uids = [l for l in u.split("\r\n") if l.startswith("UID:")]
    assert len(set(uids)) == 2 and all(x.endswith("@biocat.ai") for x in uids)


def test_ics_fda_decisions_and_skips_undated():
    evs = [{"key": "pdufa:VKTX:x", "kind": "pdufa", "date": "2027-03-14", "date_precision": "day", "confidence": "company-disclosed",
            "ticker": "VKTX", "drug": "VK2735", "title": "PDUFA", "url": "https://www.sec.gov/x"},
           {"key": "adcom:1", "kind": "adcom", "date": None, "title": "no date"}]
    u = _unfold(ics.calendar("FDA", evs, now=NOW))
    assert u.count("BEGIN:VEVENT") == 1 and "SUMMARY:VKTX PDUFA (company-disclosed): VK2735" in u
    assert "CATEGORIES:pdufa\\,company-disclosed" not in u and "CATEGORIES:pdufa,company-disclosed" in u


def test_ics_fold_keeps_utf8_intact():
    line = "SUMMARY:" + "é" * 80
    f = ics._fold(line)
    assert all(len(p.encode()) <= 75 for p in f.split("\r\n")) and f.replace("\r\n ", "") == line


def test_write_site_company_month_pages_and_sitemap(tmp_path):
    ct = FakeCT([study("NCT00000002", "2026-12-01"), study("NCT00000004", "2027-01-15"),
                 study("NCT00000005", "2026-12-20", sponsor="Tiny Private Bio GmbH")])
    rows = rc.readouts(ct, today=TODAY)
    data = page.payload(rows, "2026-11-11T00:00:00Z", [TODAY, "2027-01-26"], {})
    n = page.write_site(data, str(tmp_path))
    assert n == {"events": 3, "companies": 1, "months": 2, "urls": 6}
    for f in ("index.html", "calendar.json", "calendar.ics", "company/index.html", "company/VKTX/index.html",
              "company/VKTX/calendar.ics", "month/index.html", "month/2026-12/index.html", "month/2027-01/index.html", "sitemap.xml"):
        assert (tmp_path / f).exists(), f
    co = (tmp_path / "company/VKTX/index.html").read_text()
    assert "VKTX upcoming trial readouts" in co and "NCT00000002" in co and "NCT00000005" not in co
    assert '<link rel="canonical" href="https://biocat.ai/calendar/company/VKTX/">' in co and "application/ld+json" in co
    ld = json.loads(co.split('application/ld+json">')[1].split("</script>")[0].replace("<\\/", "</"))
    assert ld["itemListElement"][0]["item"]["startDate"] == "2026-12-01" and "(estimated)" in ld["itemListElement"][0]["item"]["name"]
    assert _unfold((tmp_path / "company/VKTX/calendar.ics").read_text()).count("BEGIN:VEVENT") == 2
    assert (tmp_path / "month/2026-12/index.html").read_text().count("<tr><td>") == 2
    sm = (tmp_path / "sitemap.xml").read_text()
    assert "https://biocat.ai/calendar/company/VKTX/" in sm and "https://biocat.ai/calendar/month/2027-01/" in sm and "<lastmod>2026-11-11" in sm
    idx = (tmp_path / "index.html").read_text()
    assert 'href="company/VKTX/"' in idx and 'href="calendar.ics"' in idx


def test_slug_is_path_safe():
    assert page.slug("brk.b") == "BRK.B" and page.slug("../etc") == "..-ETC" and "/" not in page.slug("A/B")


def test_list_watches(tmp_path):
    db = str(tmp_path / "w.db")
    assert list_watches(db) == []
    st = rc.store(db)
    st.ingest("obesity", [{"key": "a", "readout_date": "2026-12-01"}], query={"condition": "obesity", "sponsor": None}, now="2026-11-01T00:00:00+00:00")
    st.ingest("obesity", [{"key": "a", "readout_date": "2027-01-01"}, {"key": "b"}], query={"condition": "obesity"}, now="2026-11-02T00:00:00+00:00")
    ItemStore(db, "paper", ("title",)).ingest("vk", [{"key": "p"}], now="2026-10-01T00:00:00+00:00")
    from trialwatch.store import Store
    Store(db).ingest("tern", [], now="2026-11-03T00:00:00+00:00")
    w = list_watches(db)
    assert [(x["tool"], x["watch"]) for x in w] == [("trials", "tern"), ("readouts", "obesity"), ("papers", "vk")]
    r = w[1]
    assert r["runs"] == 2 and r["last_run_records"] == 2 and r["changes_stored"] == 2 and r["query"] == {"condition": "obesity"}
    assert r["snapshot_tool"] == "snapshot_readouts" and r["changes_tool"] == "readout_changes_since"
    assert [x["watch"] for x in list_watches(db, tool="papers")] == ["vk"]


def test_list_watches_mcp_tool(tmp_path, monkeypatch):
    import asyncio
    from trialwatch import mcp_server as m
    tools = {t.name: t for t in asyncio.run(m.mcp.list_tools())}
    assert "list_watches" in tools
    db = str(tmp_path / "m.db")
    rc.store(db).ingest("x", [{"key": "a"}])
    monkeypatch.setattr(m, "_db", db)
    assert m.list_watches()[0]["watch"] == "x"
    import pytest
    with pytest.raises(ValueError): m.list_watches(tool="nope")


def test_cli_ics_flags_exist():
    for mod in ("readoutwatch.cli", "decisionwatch.cli"):
        out = subprocess.run([sys.executable, "-c", f"import {mod} as c; c.main(['search', '--help'])"], capture_output=True, text=True)
        assert "--ics" in out.stdout, mod
