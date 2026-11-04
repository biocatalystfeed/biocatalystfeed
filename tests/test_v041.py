"""0.4.1: webhook alerts for watches, MCP server instructions, snapshot/changes tool descriptions."""
import hashlib, hmac, json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from biowatch import webhook, digest

CH = [{"watch": "w", "key": "NCT01234567", "nct_id": "NCT01234567", "kind": "status_change", "field": "overall_status",
       "old": "RECRUITING", "new": "TERMINATED", "severity": "critical", "title": "A trial", "detected_at": "2026-11-04T00:00:00Z"}]


class _Resp:
    def __init__(self, code): self.status_code = code


class _Sess:
    def __init__(self, codes): self.codes, self.calls = list(codes), []
    def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append((url, data, headers)); return _Resp(self.codes.pop(0))


def test_json_payload_signed_and_feed():
    s = _Sess([200])
    res = webhook.send(["https://example.test/hook"], "T", CH, "json", secret="k", session=s)
    assert res[0]["ok"] and res[0]["status"] == 200
    url, body, h = s.calls[0]
    d = json.loads(body)
    assert d["event"] == "bcf.changes" and d["count"] == 1 and d["changes"][0]["new"] == "TERMINATED"
    assert d["feed"]["version"].startswith("https://jsonfeed.org") and "advice" in d["disclaimer"]
    assert h["x-bcf-signature"] == "sha256=" + hmac.new(b"k", body, hashlib.sha256).hexdigest()


def test_no_changes_skips_unless_always():
    s = _Sess([200])
    assert webhook.send(["https://example.test/h"], "T", [], session=s) == [] and not s.calls
    assert webhook.send(["https://example.test/h"], "T", [], always=True, session=s)[0]["ok"]


def test_slack_discord_formats_and_truncation():
    many = CH * 400
    sl = webhook.payload("T", many, "slack"); dc = webhook.payload("T", many, "discord")
    assert "TERMINATED" in sl["text"] and "more" in sl["text"] and len(sl["text"]) < 4000
    assert len(dc["content"]) <= 2000 and "more" in dc["content"]
    with pytest.raises(ValueError): webhook.payload("T", CH, "xml")


def test_retry_on_5xx_then_ok_and_4xx_no_retry(monkeypatch, capsys):
    monkeypatch.setattr(webhook.time, "sleep", lambda s: None)
    s = _Sess([503, 200]); assert webhook.send(["https://e.test/h"], "T", CH, session=s)[0]["ok"] and len(s.calls) == 2
    s = _Sess([404, 200]); r = webhook.send(["https://e.test/h"], "T", CH, session=s)[0]
    assert not r["ok"] and len(s.calls) == 1 and "failed" in capsys.readouterr().err


def test_network_error_does_not_raise(monkeypatch):
    monkeypatch.setattr(webhook.time, "sleep", lambda s: None)
    class Boom:
        def post(self, *a, **k): raise ConnectionError("down")
    r = webhook.send(["https://e.test/h"], "T", CH, session=Boom())[0]
    assert not r["ok"] and "ConnectionError" in r["error"]


def test_rejects_non_http_url():
    with pytest.raises(ValueError): webhook.send(["file:///etc/passwd"], "T", CH, session=_Sess([200]))


def test_real_http_roundtrip_via_emit(tmp_path, monkeypatch):
    got = []
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            got.append((self.headers.get("x-bcf-signature"), self.rfile.read(int(self.headers["content-length"]))))
            self.send_response(204); self.end_headers()
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H); t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        import argparse
        p = argparse.ArgumentParser(); digest.add_args(p)
        a = p.parse_args(["--webhook", f"http://127.0.0.1:{srv.server_port}/x", "--rss", str(tmp_path / "f.rss")])
        monkeypatch.setenv("BCF_WEBHOOK_SECRET", "s3")
        res = digest.emit(a, CH, "BioCatalystFeed trials: w")
    finally:
        srv.shutdown()
    assert res[0]["ok"] and (tmp_path / "f.rss").exists()
    sig, body = got[0]
    assert sig == "sha256=" + hmac.new(b"s3", body, hashlib.sha256).hexdigest()


def test_every_watch_cli_accepts_webhook():
    import importlib
    for m in ("trialwatch", "fdawatch", "grantwatch", "paperwatch", "secwatch", "emawatch", "adcomwatch", "crlwatch",
              "obwatch", "decisionwatch", "readoutwatch"):
        src = open(importlib.import_module(m).__path__[0] + "/cli.py").read()
        assert "digest.emit(a," in src and "digest.write(" not in src, m


def test_mcp_instructions_and_descriptions():
    import asyncio
    from trialwatch import mcp_server as m
    assert "snapshot_" in m.INSTRUCTIONS and "baseline" in m.INSTRUCTIONS and "advice" in m.INSTRUCTIONS
    tools = asyncio.run(m.mcp.list_tools())
    d = {t.name: t.description for t in tools}
    for n in ("snapshot_grants", "snapshot_papers", "snapshot_ema", "snapshot_adcom", "snapshot_crl", "snapshot_orange_book"):
        assert "baseline" in d[n] and "local DB" in d[n], n
    for n in ("grant_changes_since", "paper_changes_since", "ema_changes_since", "crl_changes_since", "readout_changes_since"):
        assert "Returns a list" in d[n], n
