// Usage: node test/smoke.mjs [base_url]   e.g. http://127.0.0.1:8787 or https://bcf-mcp.<sub>.workers.dev
const base = (process.argv[2] || "http://127.0.0.1:8787") + "/mcp";
const H = { "content-type": "application/json", accept: "application/json, text/event-stream" };
const call = (m, params, id = 1) => fetch(base, { method: "POST", headers: H, body: JSON.stringify({ jsonrpc: "2.0", id, method: m, params }) });
const init = await (await call("initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "smoke", version: "0" } })).json();
console.log("initialize:", init.result?.serverInfo, init.result?.protocolVersion);
const tl = await (await call("tools/list", {}, 2)).json();
console.log("tools/list:", tl.result?.tools.map(t => t.name).join(", "));
const tc = await (await call("tools/call", { name: "get_trial", arguments: { nct_id: "NCT04184622" } }, 3)).json();
console.log("tools/call get_trial:", tc.result?.content?.[0]?.text?.slice(0, 160));
const codes = await Promise.all(Array.from({ length: 60 }, (_, i) => call("ping", {}, 100 + i).then(r => r.status)));
const tally = codes.reduce((m, c) => (m[c] = (m[c] || 0) + 1, m), {});
console.log("burst of 60 pings, status counts:", tally);
