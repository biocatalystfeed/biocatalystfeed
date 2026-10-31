# BioCatalystFeed hosted MCP endpoint (Cloudflare Worker)

Stateless MCP server over Streamable HTTP at `/mcp`, with per-IP rate limiting (30 req/min) via a SQLite-backed Durable Object per IP
(free plan; the Rate Limiting binding did not enforce in production). Built-in read-only tools: `search_trials`, `get_trial`, `fda_approvals`, `search_papers`,
`fda_adcom_meetings`. Setting `UPSTREAM_MCP_URL` turns it into a thin rate-limiting proxy in front of a full Python
BCF server. The production endpoint also offers the hosted-only `paper_retraction_check` tool, which is not in this source tree. Watch/snapshot tools (local SQLite state) are not offered on the hosted endpoint.

    npm install
    npx wrangler dev            # local, no account needed
    node test/smoke.mjs         # initialize, tools/list, tools/call, 60-request burst (expect 429s)
    CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... npx wrangler deploy   # -> https://bcf-mcp.<subdomain>.workers.dev/mcp

Free plan: 100k requests/day, 10 ms CPU/request (I/O wait is not counted). No DNS changes needed.
