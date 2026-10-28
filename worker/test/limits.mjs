// Usage: node test/limits.mjs [base_url]  (run against `wrangler dev --var DAILY_LIMIT_ANON:2`; local only)
const base = (process.argv[2] || "http://127.0.0.1:8787") + "/mcp";
const H = { "content-type": "application/json", "cf-connecting-ip": "203.0.113.7" };
const post = (b, h = {}) => fetch(base, { method: "POST", headers: { ...H, ...h }, body: JSON.stringify(b) });
const tc = { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "no_such_tool", arguments: {} } };
const ok = (c, m) => { if (!c) { console.error("FAIL", m); process.exit(1); } console.log("ok", m); };
for (let i = 0; i < 2; i++) ok((await post(tc)).status === 200, "call " + (i + 1) + " within quota");
const r = await post(tc), j = await r.json();
ok(r.status === 429 && j.error.code === -32002 && /daily limit reached/.test(j.error.message), "over quota -> 429/-32002");
ok(r.headers.get("x-daily-remaining") === "0" && r.headers.get("retry-after") && /x-daily-reset/.test(r.headers.get("access-control-expose-headers")), "headers + CORS expose");
ok((await post({ jsonrpc: "2.0", id: 2, method: "tools/list" })).status === 200, "tools/list not metered");
ok((await post(tc, { "x-api-key": "k" })).status === 401, "API keys off -> 401");
ok((await fetch(base.replace("/mcp", "/health"))).status === 200, "health");
