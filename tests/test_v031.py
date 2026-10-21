import copy, json
import pytest, requests
from paperwatch import core as pw
import fdawatch.client as fc
from trialwatch import cli as tcli
from trialwatch.normalize import normalize
from trialwatch.store import Store
from tests.test_trialwatch import STUDY


class FakePM:
    def esearch(self, term, mindate=None, maxdate=None, retmax=100):
        self.args = (mindate, maxdate); return 2, ["1", "2"]
    def esummary(self, ids):
        return [{"uid": "1", "title": "old", "sortpubdate": "2026/09/01 00:00"},
                {"uid": "2", "title": "new", "sortpubdate": "2026/10/15 00:00"}]


def test_pubmed_since_filters_on_displayed_date():
    pm = FakePM()
    r = pw.search_pubmed(pm, keyword="x", since="2026-10-01")
    assert [p["id"] for p in r["papers"]] == ["2"]
    assert all(p["date"] >= "2026-10-01" for p in r["papers"])
    r = pw.search_pubmed(pm, keyword="x", since="2026-08-01", until="2026-09-30")
    assert [p["id"] for p in r["papers"]] == ["1"]


def test_pubmed_esearch_uses_publication_date(monkeypatch):
    c = pw.PubMedClient(min_interval=0); seen = {}
    monkeypatch.setattr(c, "get_json", lambda url, params: seen.update(params) or {"esearchresult": {"count": 0, "idlist": []}})
    c.esearch("x", "2026-10-01")
    assert seen["datetype"] == "pdat"


def test_openfda_outage_fails_within_15s(monkeypatch):
    clock = {"t": 0.0}; calls = []
    monkeypatch.setattr(fc.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(fc.time, "sleep", lambda d: clock.__setitem__("t", clock["t"] + d))
    class S:
        headers = {}
        def get(self, url, timeout):
            calls.append(timeout); clock["t"] += timeout[0] + timeout[1]  # worst case: full timeout burned
            raise requests.Timeout("down")
    c = fc.OpenFDAClient(min_interval=0, session=S())
    with pytest.raises(requests.Timeout):
        c._get("/drug/drugsfda.json", "x", 1)
    assert len(calls) <= fc.RETRIES + 1 and clock["t"] <= 15.0 + fc.TIMEOUT[0]


def test_openfda_5xx_fails_fast(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(fc.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(fc.time, "sleep", lambda d: clock.__setitem__("t", clock["t"] + d))
    class R:
        status_code = 503; headers = {"Retry-After": "120"}
        def raise_for_status(self): raise requests.HTTPError("503")
    class S:
        headers = {}
        def get(self, url, timeout): clock["t"] += 1; return R()
    with pytest.raises(requests.HTTPError):
        fc.OpenFDAClient(min_interval=0, session=S())._get("/x", "x", 1)
    assert clock["t"] <= 15.0


def test_trials_changes_readable_and_json(tmp_path, capsys):
    db = str(tmp_path / "t.db"); st = Store(db)
    st.ingest("w", [normalize(STUDY)], now="2026-10-01T00:00:00")
    s2 = copy.deepcopy(STUDY); s2["protocolSection"]["statusModule"]["overallStatus"] = "TERMINATED"
    st.ingest("w", [normalize(s2)], now="2026-10-08T00:00:00")
    tcli.main(["--db", db, "changes", "--name", "w"])
    out = capsys.readouterr().out
    assert "NCT00000001" in out and "RECRUITING -> TERMINATED" in out and not out.lstrip().startswith("{")
    tcli.main(["--db", db, "changes", "--name", "w", "--json"])
    rows = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    assert rows and rows[0]["new"] == "TERMINATED"
