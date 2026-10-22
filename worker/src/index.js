// BioCatalystFeed hosted MCP endpoint: stateless MCP over Streamable HTTP (JSON responses), per-IP rate limited.
// Built-in read-only tools call public APIs directly (ClinicalTrials.gov, openFDA, PubMed, Federal Register).
// No request bodies or query arguments are logged; Cloudflare's platform may keep standard request logs.
import { DurableObject } from "cloudflare:workers";
const RATE_LIMIT = 30, RATE_WINDOW_MS = 60_000;

// One instance per client IP (idFromName(ip)); single-threaded, so the counter is exact.
// Stores only {window start, count}; the record is deleted by an alarm after the window ends.
export class IpRateLimiter extends DurableObject {
  async hit() {
    const now = Date.now();
    let w = (await this.ctx.storage.get("w")) || { start: now, n: 0 };
    if (now - w.start >= RATE_WINDOW_MS) w = { start: now, n: 0 };
    w.n++;
    await this.ctx.storage.put("w", w);
    if (w.n === 1) await this.ctx.storage.setAlarm(w.start + RATE_WINDOW_MS + 1000);
    return { ok: w.n <= RATE_LIMIT, remaining: Math.max(0, RATE_LIMIT - w.n), retryAfter: Math.ceil((w.start + RATE_WINDOW_MS - now) / 1000) };
  }
  async alarm() { await this.ctx.storage.deleteAll(); }
}

const PROTOCOL = "2025-06-18";
const UA = "BioCatalystFeed-hosted/0.1 (+https://github.com/biocatalystfeed/biocatalystfeed; contact@biocat.ai)";
const clamp = (n, hi, d) => Math.max(1, Math.min(Number.isFinite(+n) ? Math.floor(+n) : d, hi));

async function getJSON(url) {
  const r = await fetch(url, { headers: { "user-agent": UA, accept: "application/json" } });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`upstream ${new URL(url).host} HTTP ${r.status}`);
  return r.json();
}

function trialRow(s) {
  const p = s.protocolSection || {}, id = p.identificationModule || {}, st = p.statusModule || {};
  return {
    nct_id: id.nctId, title: id.briefTitle, status: st.overallStatus,
    phases: p.designModule?.phases || [], sponsor: p.sponsorCollaboratorsModule?.leadSponsor?.name,
    conditions: p.conditionsModule?.conditions || [],
    interventions: (p.armsInterventionsModule?.interventions || []).map(i => i.name),
    primary_completion: st.primaryCompletionDateStruct?.date, last_update_posted: st.lastUpdatePostDateStruct?.date,
    url: id.nctId ? `https://clinicaltrials.gov/study/${id.nctId}` : undefined,
  };
}

const TOOLS = {
  search_trials: {
    description: "Search ClinicalTrials.gov. phases e.g. [\"PHASE2\",\"PHASE3\"]; statuses e.g. [\"RECRUITING\"].",
    inputSchema: { type: "object", properties: {
      sponsor: { type: "string" }, condition: { type: "string" }, intervention: { type: "string" },
      phases: { type: "array", items: { type: "string" } }, statuses: { type: "array", items: { type: "string" } },
      max_records: { type: "integer", default: 20, maximum: 100 } } },
    async run(a) {
      const q = new URLSearchParams({ format: "json", pageSize: String(clamp(a.max_records, 100, 20)) });
      if (a.sponsor) q.set("query.spons", a.sponsor);
      if (a.condition) q.set("query.cond", a.condition);
      if (a.intervention) q.set("query.intr", a.intervention);
      if (a.statuses?.length) q.set("filter.overallStatus", a.statuses.join(","));
      if (a.phases?.length) q.set("filter.advanced", a.phases.map(p => `AREA[Phase]${p}`).join(" OR "));
      const d = await getJSON(`https://clinicaltrials.gov/api/v2/studies?${q}`);
      return (d?.studies || []).map(trialRow);
    } },
  get_trial: {
    description: "Get one trial record from ClinicalTrials.gov by NCT ID.",
    inputSchema: { type: "object", properties: { nct_id: { type: "string" } }, required: ["nct_id"] },
    async run(a) {
      if (!/^NCT\d{8}$/i.test(a.nct_id || "")) throw new Error("nct_id must look like NCT01234567");
      const d = await getJSON(`https://clinicaltrials.gov/api/v2/studies/${a.nct_id.toUpperCase()}?format=json`);
      if (!d) throw new Error("trial not found");
      return trialRow(d);
    } },
  fda_approvals: {
    description: "Drugs@FDA submissions from openFDA (Data provided by the U.S. FDA). Filter by sponsor name.",
    inputSchema: { type: "object", properties: { sponsor: { type: "string" }, max_results: { type: "integer", default: 20, maximum: 100 } },
      required: ["sponsor"] },
    async run(a) {
      const s = String(a.sponsor).replace(/["\\]/g, "").toUpperCase();
      const d = await getJSON(`https://api.fda.gov/drug/drugsfda.json?search=sponsor_name:"${encodeURIComponent(s)}"&limit=${clamp(a.max_results, 100, 20)}`);
      return (d?.results || []).map(r => ({
        application_number: r.application_number, sponsor: r.sponsor_name,
        brand_names: [...new Set((r.products || []).map(p => p.brand_name))],
        submissions: (r.submissions || []).slice(0, 5).map(x => ({ type: x.submission_type, number: x.submission_number, status: x.submission_status, date: x.submission_status_date })),
      }));
    } },
  search_papers: {
    description: "Search PubMed (NCBI E-utilities); returns citation metadata and links only.",
    inputSchema: { type: "object", properties: { keyword: { type: "string" }, max_records: { type: "integer", default: 10, maximum: 50 } }, required: ["keyword"] },
    async run(a) {
      const e = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils";
      const s = await getJSON(`${e}/esearch.fcgi?db=pubmed&retmode=json&sort=pub_date&tool=biocatalystfeed&email=contact@biocat.ai&retmax=${clamp(a.max_records, 50, 10)}&term=${encodeURIComponent(a.keyword)}`);
      const ids = s?.esearchresult?.idlist || [];
      if (!ids.length) return [];
      const m = await getJSON(`${e}/esummary.fcgi?db=pubmed&retmode=json&tool=biocatalystfeed&email=contact@biocat.ai&id=${ids.join(",")}`);
      return ids.map(id => m.result[id]).filter(Boolean).map(r => ({ pmid: r.uid, title: r.title, journal: r.fulljournalname, pubdate: r.pubdate, url: `https://pubmed.ncbi.nlm.nih.gov/${r.uid}/` }));
    } },
  fda_adcom_meetings: {
    description: "FDA advisory committee meeting notices from the Federal Register.",
    inputSchema: { type: "object", properties: { since: { type: "string", description: "YYYY-MM-DD" }, max_results: { type: "integer", default: 20, maximum: 100 } } },
    async run(a) {
      const q = new URLSearchParams({ "conditions[agencies][]": "food-and-drug-administration", "conditions[type][]": "NOTICE",
        "conditions[term]": "\"advisory committee\" meeting", per_page: String(clamp(a.max_results, 100, 20)), order: "newest" });
      if (a.since && /^\d{4}-\d{2}-\d{2}$/.test(a.since)) q.set("conditions[publication_date][gte]", a.since);
      const d = await getJSON(`https://www.federalregister.gov/api/v1/documents.json?${q}`);
      return (d?.results || []).map(r => ({ title: r.title, publication_date: r.publication_date, document_number: r.document_number, url: r.html_url }));
    } },
};

const json = (body, status = 200, extra = {}) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "access-control-allow-origin": "*", ...extra } });
const rpcErr = (id, code, message) => ({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });

async function handleRpc(msg) {
  const { id, method, params = {} } = msg || {};
  if (id === undefined) return null; // notification
  switch (method) {
    case "initialize":
      return { jsonrpc: "2.0", id, result: { protocolVersion: PROTOCOL, capabilities: { tools: { listChanged: false } },
        serverInfo: { name: "biocatalystfeed-hosted", version: "0.1.0" },
        instructions: "Read-only public biotech data. Not investment, legal or medical advice. Sources: ClinicalTrials.gov, openFDA, PubMed, Federal Register." } };
    case "ping": return { jsonrpc: "2.0", id, result: {} };
    case "tools/list":
      return { jsonrpc: "2.0", id, result: { tools: Object.entries(TOOLS).map(([name, t]) => ({ name, description: t.description, inputSchema: t.inputSchema, annotations: { readOnlyHint: true, openWorldHint: true } })) } };
    case "tools/call": {
      const t = TOOLS[params.name];
      if (!t) return rpcErr(id, -32602, `unknown tool: ${params.name}`);
      try {
        const out = await t.run(params.arguments || {});
        return { jsonrpc: "2.0", id, result: { content: [{ type: "text", text: JSON.stringify(out) }], structuredContent: { result: out } } };
      } catch (e) {
        return { jsonrpc: "2.0", id, result: { isError: true, content: [{ type: "text", text: String(e.message || e) }] } };
      }
    }
    default: return rpcErr(id, -32601, `method not found: ${method}`);
  }
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-methods": "POST, GET, DELETE, OPTIONS", "access-control-allow-headers": "content-type, accept, mcp-session-id, mcp-protocol-version" } });
    if (url.pathname === "/" || url.pathname === "/health") return json({ ok: true, service: "BioCatalystFeed hosted MCP", endpoint: "/mcp", terms: "https://github.com/biocatalystfeed/biocatalystfeed/blob/main/TERMS.md", privacy: "https://github.com/biocatalystfeed/biocatalystfeed/blob/main/PRIVACY.md" });
    if (url.pathname !== "/mcp") return json({ error: "not found" }, 404);

    const ip = req.headers.get("cf-connecting-ip") || "unknown";
    let rl = {};
    if (env.LIMITER) {
      const r = await env.LIMITER.get(env.LIMITER.idFromName(ip)).hit();
      if (!r.ok) return json(rpcErr(null, -32000, `rate limit exceeded (${RATE_LIMIT} requests/minute per IP); retry later`), 429, { "retry-after": String(Math.max(1, r.retryAfter)), "x-ratelimit-limit": String(RATE_LIMIT), "x-ratelimit-remaining": "0" });
      rl = { "x-ratelimit-limit": String(RATE_LIMIT), "x-ratelimit-remaining": String(r.remaining) };
    }
    if (req.method === "GET") return json(rpcErr(null, -32000, "SSE stream not supported; use POST"), 405, { allow: "POST" });
    if (req.method === "DELETE") return new Response(null, { status: 204 });
    if (req.method !== "POST") return json(rpcErr(null, -32000, "method not allowed"), 405);

    if (env.UPSTREAM_MCP_URL) { // thin-proxy mode to a full Python BCF server
      const h = new Headers(req.headers); h.delete("cookie");
      return fetch(env.UPSTREAM_MCP_URL, { method: "POST", headers: h, body: req.body });
    }
    let body;
    try { body = await req.json(); } catch { return json(rpcErr(null, -32700, "parse error"), 400); }
    if (Array.isArray(body)) {
      const out = (await Promise.all(body.slice(0, 10).map(handleRpc))).filter(Boolean);
      return out.length ? json(out, 200, rl) : new Response(null, { status: 202 });
    }
    const out = await handleRpc(body);
    return out ? json(out, 200, rl) : new Response(null, { status: 202 });
  },
};
