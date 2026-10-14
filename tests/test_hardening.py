"""Launch hardening: backoff on 429/5xx/network errors, Retry-After, input validation, friendly CLI errors."""
import pytest, requests
from biowatch import http
from biowatch.http import Throttled, retry_delay
from trialwatch.client import CTGovClient, validate_nct


class Resp:
    def __init__(self, code, headers=None, url="https://x.test/a"):
        self.status_code, self.headers, self.url = code, headers or {}, url
    def json(self): return {"ok": True}
    def raise_for_status(self):
        if self.status_code >= 400: raise requests.HTTPError(f"{self.status_code}", response=self)


class Sess:
    def __init__(self, seq): self.seq, self.headers, self.n = list(seq), {}, 0
    def _next(self, *a, **k):
        self.n += 1; x = self.seq.pop(0)
        if isinstance(x, Exception): raise x
        return x
    request = get = _next


@pytest.fixture(autouse=True)
def nosleep(monkeypatch):
    slept = []
    monkeypatch.setattr(http.time, "sleep", slept.append)
    import trialwatch.client as tc, fdawatch.client as fc
    monkeypatch.setattr(tc.time, "sleep", slept.append); monkeypatch.setattr(fc.time, "sleep", slept.append)
    return slept


def test_retry_after_honoured_and_capped():
    assert retry_delay(0, Resp(429, {"Retry-After": "7"})) == 7
    assert retry_delay(0, Resp(429, {"Retry-After": "9999"})) == http.MAX_WAIT
    d = retry_delay(3); assert 8 <= d <= 16  # jittered exponential


def test_throttled_retries_429_then_succeeds(nosleep):
    s = Sess([Resp(429, {"Retry-After": "2"}), Resp(503), Resp(200)])
    assert Throttled(min_interval=0, session=s).get_json("https://x.test") == {"ok": True}
    assert s.n == 3 and 2 in nosleep


def test_throttled_retries_connection_errors():
    s = Sess([requests.ConnectionError("boom"), Resp(200)])
    assert Throttled(min_interval=0, session=s).get_json("https://x.test") == {"ok": True}


def test_throttled_gives_up_after_4():
    s = Sess([Resp(503)] * 4)
    with pytest.raises(requests.HTTPError): Throttled(min_interval=0, session=s).get_json("https://x.test")
    assert s.n == 4


def test_ctgov_backoff():
    s = Sess([Resp(429), Resp(200)])
    assert CTGovClient(min_interval=0, session=s)._get("/studies", {}) == {"ok": True}


def test_nct_validation():
    assert validate_nct(" nct04184622 ") == "NCT04184622"
    for bad in ["NCT123", "../../version", "NCT04184622/../x", ""]:
        with pytest.raises(ValueError): validate_nct(bad)


def test_mcp_clamp_and_feed_validation():
    from trialwatch import mcp_server as m
    assert m._clamp(10**9, 500) == 500 and m._clamp(-5, 500) == 1
    with pytest.raises(ValueError): m.changes_feed(tool="../etc")
    with pytest.raises(ValueError): m.get_trial("NCT1/../../x")


def test_cli_friendly_errors(capsys):
    from biocatalystfeed.cli import main
    assert main(["trials", "search", "--phase", "PHASE9"]) == 1
    err = capsys.readouterr().err
    assert "unknown phase" in err and "Traceback" not in err
