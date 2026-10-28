"""0.3.4: sponsor alias expansion for trial search/watch/pipeline; MCP parameter descriptions + tool annotations."""
import pytest
from trialwatch.core import sponsor_queries, raw_search, search, run_watch
from trialwatch.store import Store


def _st(nct, sponsor):
    return {"protocolSection": {"identificationModule": {"nctId": nct, "briefTitle": f"t {nct}"},
                                "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor}},
                                "statusModule": {"overallStatus": "RECRUITING"}}}


class FakeCT:
    """CT.gov free text: 'Terns Pharmaceuticals' matches nothing, 'Terns, Inc.' matches the Merck subsidiary, 'TERN'
    matches an unrelated company."""
    DATA = {"Terns, Inc.": [_st("NCT00000001", "Terns, Inc., a subsidiary of Merck & Co., Inc."),
                            _st("NCT00000002", "Terns, Inc., a subsidiary of Merck & Co., Inc.")],
            "Terns Pharmaceuticals": [],
            "TERN": [_st("NCT09999999", "Tern Therapeutics, LLC")],
            "Acme Bio": [_st("NCT00000003", "Acme Bio")]}

    def __init__(self): self.calls = []

    def search(self, max_records=500, extra_fields=None, **kw):
        self.calls.append(kw.get("sponsor"))
        return list(self.DATA.get(kw.get("sponsor"), []))[:max_records]


def test_sponsor_queries():
    assert sponsor_queries("Terns Pharmaceuticals") == ["Terns Pharmaceuticals", "Terns, Inc."]
    assert sponsor_queries("TERN") == ["Terns, Inc.", "Terns Pharmaceuticals"]  # bare ticker not sent as free text
    assert sponsor_queries("Viking Therapeutics") == ["Viking Therapeutics"]
    assert sponsor_queries("Acme Bio") == ["Acme Bio"]
    assert sponsor_queries(None) == [None]


def test_alias_search_finds_renamed_sponsor_and_dedupes():
    ct = FakeCT()
    rows = search(ct, sponsor="Terns Pharmaceuticals", max_records=50)
    assert [r["nct_id"] for r in rows] == ["NCT00000001", "NCT00000002"]
    assert ct.calls == ["Terns Pharmaceuticals", "Terns, Inc."]
    assert [r["nct_id"] for r in search(FakeCT(), sponsor="TERN")] == ["NCT00000001", "NCT00000002"]
    assert search(FakeCT(), sponsor="Terns Pharmaceuticals", sponsor_aliases=False) == []
    assert len(raw_search(FakeCT(), sponsor="Terns Pharmaceuticals", max_records=1)) == 1
    ct = FakeCT(); assert [r["nct_id"] for r in search(ct, sponsor="Acme Bio")] == ["NCT00000003"] and ct.calls == ["Acme Bio"]


def test_watch_uses_aliases(tmp_path):
    info = run_watch(FakeCT(), Store(str(tmp_path / "t.db")), "terns", sponsor="Terns Pharmaceuticals")
    assert info["records"] == 2


def test_cli_no_aliases_flag(monkeypatch, capsys):
    from trialwatch import cli
    monkeypatch.setattr(cli, "CTGovClient", FakeCT)
    cli.main(["search", "--sponsor", "Terns Pharmaceuticals", "--json"])
    assert "NCT00000001" in capsys.readouterr().out
    cli.main(["search", "--sponsor", "Terns Pharmaceuticals", "--json", "--no-aliases"])
    assert "NCT00000001" not in capsys.readouterr().out


def test_mcp_params_described_and_annotated():
    pytest.importorskip("mcp")
    from trialwatch import mcp_server as m
    tools = m.mcp._tool_manager._tools if hasattr(m.mcp, "_tool_manager") else {}
    if not tools: pytest.skip("tool registry not introspectable on this SDK")
    missing = [f"{n}.{p}" for n, t in tools.items() for p, s in t.parameters["properties"].items() if not s.get("description")]
    assert missing == []
    for n, t in tools.items():
        a = t.annotations
        assert a is not None, n
        if n.startswith("snapshot_"):
            assert a.read_only_hint is False and a.destructive_hint is False
        elif n.endswith("_changes_since") or n == "changes_feed":
            assert a.read_only_hint is True and a.open_world_hint is False
        else:
            assert a.read_only_hint is True and a.open_world_hint is True
