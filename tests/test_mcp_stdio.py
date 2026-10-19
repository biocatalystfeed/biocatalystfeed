"""Spawn the MCP server over stdio and list tools (no network needed)."""
import asyncio, sys, pytest
mcp = pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_list_tools(tmp_path):
    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "trialwatch.mcp_server"],
                                       env={"TRIALWATCH_DB": str(tmp_path / "m.db"), "PATH": "/usr/bin:/bin"})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return {t.name for t in (await s.list_tools()).tools}
    names = asyncio.run(go())
    assert {"search_trials", "get_trial", "trial_changes_since", "sponsor_pipeline", "snapshot_watch", "fda_approvals", "company_profile", "fda_changes_since", "search_grants", "grant_changes_since", "search_papers", "paper_changes_since", "sec_pdufa_mentions", "snapshot_grants", "snapshot_papers", "changes_feed", "ema_medicines", "snapshot_ema", "ema_changes_since"} <= names
