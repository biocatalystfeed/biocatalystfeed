"""MCP Registry server.json constraints (length limits that caused 0.4.4 to be rejected)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Official schema: https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json
# ServerDetail.description maxLength 100, title maxLength 100, name maxLength 200, version maxLength 255.
LIMITS = {
    "description": 100,
    "title": 100,
    "name": 200,
    "version": 255,
}


def test_server_json_fields_fit_mcp_registry_limits():
    d = json.loads((ROOT / "server.json").read_text())
    for field, limit in LIMITS.items():
        value = d[field]
        assert isinstance(value, str) and value, field
        assert len(value) <= limit, f"{field} is {len(value)} chars; MCP Registry limit is {limit}"
    for pkg in d.get("packages") or []:
        ver = pkg.get("version")
        assert ver == d["version"], f"package {pkg.get('identifier')} version {ver} != server version {d['version']}"
