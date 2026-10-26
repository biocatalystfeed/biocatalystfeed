// Usage: node test/crl.mjs [base_url]  (tools/list includes fda_complete_response_letters; one live call)
const base = (process.argv[2] || "http://127.0.0.1:8787") + "/mcp";
const rpc = async (method, params) => (await (await fetch(base, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) })).json()).result;
console.log("tools:", (await rpc("tools/list", {})).tools.map(t => t.name).join(", "));
const r = await rpc("tools/call", { name: "fda_complete_response_letters", arguments: { since: "2026-01-01", max_results: 3 } });
console.log(r.isError ? "ERROR " + r.content[0].text : JSON.stringify(r.structuredContent.result, null, 1).slice(0, 900));
const k = await rpc("tools/call", { name: "fda_complete_response_letters", arguments: { topic: "facility", max_results: 2 } });
console.log("facility topic:", k.isError ? k.content[0].text : k.structuredContent.result.map(x => [x.letter_date, x.company, x.topics]));
