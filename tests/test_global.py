"""Phase 1 opt-in Global coverage: labels, link-outs, disclaimer, defaults unchanged (no network)."""
import json, sys
import pytest
from biowatch import globalcov as gc, digest
from trialwatch import cli as tcli
from tests.test_trialwatch import STUDY
import copy


def test_registry_links_label_and_link_only():
    out = gc.registry_links([{"id": "ChiCTR2400081234", "type": "REGISTRY"}, "CTRI/2023/11/059758", "ISRCTN12345678",
                             "EudraCT 2020-000001-11", "ChiCTR2400081234"], "NCT01234567")
    assert [o["registry"] for o in out] == ["ChiCTR", "WHO-ICTRP:CTRI", "WHO-ICTRP:ISRCTN"]
    for o in out:
        assert o["registry_class"] == "non-FDA/EMA registry" and o["link_only"] is True
        assert o["also_registered_as"] == "NCT01234567" and o["source_url"].startswith("https://")
    assert gc.text_label(out[0]) == "[non-FDA/EMA registry] ChiCTR (China)"


def test_global_sources_filter_and_validation():
    assert [o["registry"] for o in gc.registry_links(["ChiCTR2400081234", "KCT0001234"], sources={"chictr"})] == ["ChiCTR"]
    assert gc.parse_sources("chictr,ictrp") == {"chictr", "ictrp"}
    assert gc.parse_sources(None) is None
    with pytest.raises(ValueError): gc.parse_sources("cnki")


@pytest.mark.parametrize("affs,flag", [
    (["Dept of Endocrinology, Peking Union Medical College Hospital, Beijing, China."], "non-FDA/EMA oversight"),
    (["Harvard Medical School, Boston, MA, USA", "Charité, Berlin, Germany"], None),
    (["University of New Mexico, Albuquerque, NM"], "unknown"),
    ([], "unknown"),
    (["Mayo Clinic, USA", "Fudan University, Shanghai, P.R. China"], "non-FDA/EMA oversight"),
])
def test_paper_flag_never_guesses(affs, flag):
    assert gc.paper_flag(affs)[0] == flag


def test_annotate_and_disclaimer_text():
    ps = [{"key": "pmid:1"}, {"key": "pmid:2"}]
    gc.annotate_papers(ps, {"pmid:1": ["Tokyo, Japan"]})
    assert ps[0]["jurisdiction_flag"] == "non-FDA/EMA oversight" and ps[0]["registry_class"] == "non-FDA/EMA registry"
    assert ps[1]["jurisdiction_flag"] == "unknown" and "registry_class" not in ps[1]
    assert gc.text_label(ps[0]).startswith("[non-FDA/EMA oversight]")
    assert "not medical, legal or investment advice" in gc.GLOBAL_DISCLAIMER
    assert "sometimes lighter than" in gc.GLOBAL_DISCLAIMER


def test_lookup_affiliations_maps_by_pmid_and_doi():
    class E:
        def search(self, q, max_records):
            return 2, [{"pmid": "1", "authorList": {"author": [{"authorAffiliationDetailsList": {"authorAffiliation": [{"affiliation": "Seoul, Korea"}]}}]}},
                       {"doi": "10.1/X", "affiliation": "Paris, France"}]
    m = gc.lookup_affiliations(E(), [{"key": "pmid:1", "source": "pubmed", "id": "1"}, {"key": "doi:10.1/x", "doi": "10.1/X"}])
    assert m == {"pmid:1": ["Seoul, Korea"], "doi:10.1/x": ["Paris, France"]}


def test_digest_labels_global_items():
    c = {"kind": "new", "title": "T", "registry_class": "non-FDA/EMA registry", "url": "https://x"}
    f = digest.json_feed("t", [c, {"kind": "new", "title": "U"}])
    assert f["items"][0]["title"].startswith("[non-FDA/EMA registry]") and gc.GLOBAL_DISCLAIMER in f["items"][0]["content_text"]
    assert gc.GLOBAL_DISCLAIMER not in f["items"][1]["content_text"]
    assert "[non-FDA/EMA registry]" in digest.rss("t", [c])


class FakeCL:
    def __init__(self): self.calls = []
    def search(self, max_records=200, extra_fields=None, **q):
        self.calls.append(extra_fields)
        s = copy.deepcopy(STUDY)
        s["protocolSection"]["identificationModule"]["secondaryIdInfos"] = [{"id": "ChiCTR2400081234"}]
        return [s]


def _run(monkeypatch, capsys, argv, tty=False):
    cl = FakeCL(); monkeypatch.setattr(tcli, "CTGovClient", lambda: cl)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: tty, raising=False)
    tcli.main(argv); o = capsys.readouterr(); return cl, o


def test_trials_default_unchanged(monkeypatch, capsys):
    cl, o = _run(monkeypatch, capsys, ["search", "--sponsor", "x", "--json"])
    rows = json.loads(o.out)
    assert isinstance(rows, list) and "global_links" not in rows[0] and cl.calls == [None]
    assert "non-FDA" not in o.out and "tip:" not in o.err


def test_trials_global_json_and_text(monkeypatch, capsys):
    cl, o = _run(monkeypatch, capsys, ["search", "--sponsor", "x", "--json", "--global"])
    d = json.loads(o.out)
    assert d["global_disclaimer"] == gc.GLOBAL_DISCLAIMER and cl.calls == [["SecondaryIdInfo"]]
    assert d["trials"][0]["global_links"][0]["registry_class"] == "non-FDA/EMA registry"
    _, o = _run(monkeypatch, capsys, ["search", "--sponsor", "x", "--global"])
    assert o.out.splitlines()[0] == gc.HEADER
    assert "[non-FDA/EMA registry] ChiCTR (China) ChiCTR2400081234" in o.out
    assert o.out.count(gc.GLOBAL_DISCLAIMER) == 1


def test_tip_only_on_tty_and_suppressible(monkeypatch, capsys):
    _, o = _run(monkeypatch, capsys, ["search", "--sponsor", "x"], tty=True)
    assert gc.TIP in o.err and gc.TIP not in o.out
    _, o = _run(monkeypatch, capsys, ["search", "--sponsor", "x", "--quiet"], tty=True)
    assert gc.TIP not in o.err
    monkeypatch.setenv("BCF_NO_TIPS", "1")
    _, o = _run(monkeypatch, capsys, ["search", "--sponsor", "x"], tty=True)
    assert gc.TIP not in o.err


def test_bcf_global_help(capsys):
    from biocatalystfeed.cli import main
    assert main(["--global", "--help"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("--global   Opt-in.") and "--global-sources LIST" in out and "not medical," in out


def test_mcp_signatures_default_off():
    import inspect
    from trialwatch import mcp_server as m
    for f in (m.search_trials, m.search_papers):
        sig = inspect.signature(f)
        assert sig.parameters["include_global"].default is False
        assert "Set `include_global: true`" in f.__doc__ and "Off by default." in f.__doc__


def test_no_ingest_of_blocked_sources():
    import inspect
    src = inspect.getsource(gc)
    assert "chictr.org.cn" not in src and "chinadrugtrials" not in src
