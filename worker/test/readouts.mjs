// Usage: node test/readouts.mjs [base_url]  (readout_calendar, trials_at_risk, /calendar.json, provenance; live calls)
const root = process.argv[2] || "http://127.0.0.1:8787", base = root + "/mcp";
const rpc = async (method, params) => (await (await fetch(base, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) })).json()).result;
const tools = (await rpc("tools/list", {})).tools; console.log("tools:", tools.length, tools.map(t => t.name).join(", "));
const r = await rpc("tools/call", { name: "readout_calendar", arguments: { upcoming_days: 30, max_results: 5 } });
if (r.isError) throw new Error(r.content[0].text);
const x = r.structuredContent.result; console.log("window", x.window, JSON.stringify(x.readouts.map(e => [e.readout_date, e.readout_date_type, e.ticker, e.ticker_confidence, e.sponsor, e.nct_id])));
console.log("provenance", JSON.stringify({ v: x.readouts[0].verified_as_of, h: x.readouts[0].verify_hash, s: x.readouts[0].source_url }));
const v = await rpc("tools/call", { name: "readout_calendar", arguments: { sponsor: "VKTX", upcoming_days: 720 } });
console.log("VKTX", JSON.stringify(v.structuredContent.result.readouts.map(e => [e.readout_date, e.ticker, e.nct_id])));
const k = await rpc("tools/call", { name: "trials_at_risk", arguments: { condition: "obesity", max_results: 5 } });
console.log("risk", JSON.stringify(k.structuredContent.result.trials.map(e => [e.risk_score, e.nct_id, e.ticker, e.risk_flags.map(f => f.flag).join("+")])));
const c = await (await fetch(root + "/calendar.json")).json(); console.log("calendar.json", c.count, c.window, c.generated_at);
