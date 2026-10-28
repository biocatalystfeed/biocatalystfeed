// Usage: node test/decisions.mjs [base_url]  (tools/list includes fda_decisions; live calls)
const base = (process.argv[2] || "http://127.0.0.1:8787") + "/mcp";
const rpc = async (method, params) => (await (await fetch(base, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) })).json()).result;
console.log("tools:", (await rpc("tools/list", {})).tools.map(t => t.name).join(", "));
const r = await rpc("tools/call", { name: "fda_decisions", arguments: { upcoming_days: 120, max_results: 8 } });
console.log(r.isError ? "ERROR " + r.content[0].text : JSON.stringify(r.structuredContent.result.events.map(e => [e.date, e.kind, e.confidence, e.ticker, e.title.slice(0, 70)]), null, 0), r.structuredContent?.result?.errors);
const s = await rpc("tools/call", { name: "fda_decisions", arguments: { drug: "semaglutide", kinds: ["approval", "crl"], since: "2025-01-01", max_results: 4 } });
console.log(s.isError ? "ERROR " + s.content[0].text : JSON.stringify(s.structuredContent.result.events.map(e => [e.date, e.kind, e.title.slice(0, 60)])));
