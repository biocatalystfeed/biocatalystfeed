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
const UA = "BioCatalystFeed-hosted/0.3.2 (+https://github.com/biocatalystfeed/biocatalystfeed; contact@biocat.ai)";
const clamp = (n, hi, d) => Math.max(1, Math.min(Number.isFinite(+n) ? Math.floor(+n) : d, hi));

async function getJSON(url) {
  let r;
  try { r = await fetch(url, { headers: { "user-agent": UA, accept: "application/json" }, signal: AbortSignal.timeout(15000) }); }
  catch (e) { throw new Error(`upstream ${new URL(url).host} unavailable (${e.name === "TimeoutError" ? "timed out after 15 s" : "network error"}); try again later`); }
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

// ---- Opt-in Global coverage, Phase 1 (off by default): labelled link-outs + paper jurisdiction flags only.
// No WHO ICTRP data, ChiCTR pages or NMPA/CDE platform data is fetched or stored; we only link to registry IDs that
// ClinicalTrials.gov already lists as secondary IDs. Mirrors biowatch/globalcov.py.
const REGISTRY_CLASS = "non-FDA/EMA registry", PAPER_FLAG = "non-FDA/EMA oversight";
const GLOBAL_DISCLAIMER = "Results labelled \"non-FDA/EMA registry\" come from registries and studies that may operate under regulatory, ethics and data standards different from, and sometimes lighter than, those of the US FDA or the EU's EMA. They are included because you opted in to see everything that is out there. Inclusion is not an endorsement or recommendation and is not medical, legal or investment advice.";
const ICTRP = id => `https://trialsearch.who.int/Trial2.aspx?TrialID=${encodeURIComponent(id)}`;
const REGISTRIES = [
  ["ChiCTR", "chictr", "China", /ChiCTR[-A-Z]*\d{6,}/, ICTRP], ["WHO-ICTRP:CTRI", "ictrp", "India", /CTRI\/\d{4}\/\d{2,3}\/\d{6}/, ICTRP],
  ["WHO-ICTRP:jRCT", "ictrp", "Japan", /jRCT[a-z]?\d{7,10}/, ICTRP], ["WHO-ICTRP:JPRN", "ictrp", "Japan", /JPRN-[A-Za-z]+-?\d+/, ICTRP],
  ["WHO-ICTRP:CRIS", "ictrp", "South Korea", /KCT\d{7}/, ICTRP], ["WHO-ICTRP:ANZCTR", "ictrp", "Australia/New Zealand", /ACTRN\d{14}/, ICTRP],
  ["WHO-ICTRP:ReBEC", "ictrp", "Brazil", /RBR-[0-9a-z]{6,8}/, ICTRP], ["WHO-ICTRP:PACTR", "ictrp", "Africa", /PACTR\d{15,16}/, ICTRP],
  ["WHO-ICTRP:IRCT", "ictrp", "Iran", /IRCT\d{8,}N\d+/, ICTRP], ["WHO-ICTRP:TCTR", "ictrp", "Thailand", /TCTR\d{11}/, ICTRP],
  ["WHO-ICTRP:ISRCTN", "ictrp", "United Kingdom/international", /ISRCTN\d{8}/, id => `https://www.isrctn.com/${id}`],
];
const GLOBAL_SOURCES = ["chictr", "nmpa", "ictrp"];
function parseSources(v) {
  if (!v || !v.length) return null;
  const s = (Array.isArray(v) ? v : String(v).split(",")).map(x => String(x).trim().toLowerCase()).filter(Boolean);
  const bad = s.filter(x => !GLOBAL_SOURCES.includes(x));
  if (bad.length) throw new Error(`unknown global source(s) ${bad.join(", ")}; choose from ${GLOBAL_SOURCES.join(", ")}`);
  return new Set(s);
}
function registryLinks(study, srcs) {
  const nct = study.protocolSection?.identificationModule?.nctId, out = [], seen = new Set();
  for (const s of study.protocolSection?.identificationModule?.secondaryIdInfos || []) {
    for (const [reg, key, juris, rx, url] of REGISTRIES) {
      if (srcs && !srcs.has(key)) continue;
      const m = String(s.id || "").match(rx);
      if (m && !seen.has(m[0])) { seen.add(m[0]); out.push({ registry_class: REGISTRY_CLASS, registry: reg, registry_id: m[0], jurisdiction: juris, source_url: url(m[0]), also_registered_as: nct, link_only: true }); }
    }
  }
  return out;
}
const HOME = ["United States", "USA", "U.S.A.", "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic", "Czechia", "Denmark", "Estonia", "Finland", "France", "Germany", "Greece", "Hungary", "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta", "Netherlands", "The Netherlands", "Poland", "Portugal", "Romania", "Slovakia", "Slovenia", "Spain", "Sweden", "Iceland", "Liechtenstein", "Norway"];
const OTHER = ["China", "P.R. China", "PR China", "Hong Kong", "Macau", "Taiwan", "Japan", "Korea", "Republic of Korea", "India", "Iran", "Brazil", "United Kingdom", "UK", "England", "Scotland", "Wales", "Northern Ireland", "Switzerland", "Canada", "Australia", "New Zealand", "Russia", "Russian Federation", "Turkey", "Türkiye", "Israel", "Egypt", "Saudi Arabia", "Pakistan", "Singapore", "Mexico", "South Africa", "Nigeria", "Thailand", "Vietnam", "Viet Nam", "Malaysia", "Indonesia", "Argentina", "Chile", "Colombia", "Peru", "Bangladesh", "Philippines", "Ukraine", "Serbia", "Qatar", "United Arab Emirates", "UAE", "Jordan", "Lebanon", "Ethiopia", "Kenya", "Ghana", "Uganda", "Tanzania", "Morocco", "Tunisia", "Nepal", "Sri Lanka", "Kazakhstan", "Belarus"];
const CANON = { "USA": "United States", "U.S.A.": "United States", "Czechia": "Czech Republic", "The Netherlands": "Netherlands", "P.R. China": "China", "PR China": "China", "Republic of Korea": "South Korea", "Korea": "South Korea", "UK": "United Kingdom", "England": "United Kingdom", "Scotland": "United Kingdom", "Wales": "United Kingdom", "Northern Ireland": "United Kingdom", "Russian Federation": "Russia", "Türkiye": "Turkey", "Viet Nam": "Vietnam", "UAE": "United Arab Emirates" };
const HOME_SET = new Set(HOME.map(c => CANON[c] || c));
const reEsc = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const COUNTRY_RX = new RegExp("(?<![A-Za-z])(?<!New )(?<!New South )(" + [...new Set([...HOME, ...OTHER])].sort((a, b) => b.length - a.length).map(reEsc).join("|") + ")(?![A-Za-z])", "g");
function paperFlag(affs) {
  const found = [];
  for (let a of affs || []) {
    a = String(a).replace(/\S+@\S+/g, " ");
    for (const m of a.matchAll(COUNTRY_RX)) { const c = CANON[m[1]] || m[1]; if (c === "Ireland" && a.includes("Northern Ireland")) continue; if (!found.includes(c)) found.push(c); }
  }
  if (!found.length) return ["unknown", []];
  return [found.some(c => !HOME_SET.has(c)) ? PAPER_FLAG : null, found];
}
async function epmcAffiliations(pmids) { // Europe PMC core metadata (author affiliations) by PMID; metadata only
  const q = pmids.map(id => `(EXT_ID:${id} AND SRC:MED)`).join(" OR ");
  const d = await getJSON(`https://www.ebi.ac.uk/europepmc/webservices/rest/search?format=json&resultType=core&pageSize=${pmids.length * 2}&query=${encodeURIComponent(q)}`);
  const out = {};
  for (const r of d?.resultList?.result || []) {
    const affs = [];
    for (const au of r.authorList?.author || []) {
      for (const x of au.authorAffiliationDetailsList?.authorAffiliation || []) if (x.affiliation) affs.push(x.affiliation);
      if (au.affiliation) affs.push(au.affiliation);
    }
    if (!affs.length && r.affiliation) affs.push(r.affiliation);
    if (r.pmid && !out[r.pmid]) out[r.pmid] = affs;
  }
  return out;
}
const INCLUDE_GLOBAL_DESC = "Opt-in. Adds non-FDA/EMA sources that may follow different, sometimes lighter, regulatory standards. Results are labelled. Not an endorsement or medical or investment advice.";
const GLOBAL_SOURCES_DESC = "Optional, with include_global: limit to e.g. [\"chictr\",\"ictrp\"].";

const TOOLS = {
  search_trials: {
    description: "Search clinical trials (ClinicalTrials.gov by default). Set `include_global: true` to also include non-FDA/EMA registries (China's ChiCTR and NMPA platform, other WHO ICTRP registries). Global results carry `registry_class: \"non-FDA/EMA registry\"` and a `global_disclaimer`. Off by default. Phase 1: global results are link-outs (registry ID + URL from ClinicalTrials.gov secondary IDs, in each trial's global_links); foreign registry records are not ingested. When showing global results to a user, keep the label and the disclaimer. Most recently updated first; phases e.g. [\"PHASE2\",\"PHASE3\"]; statuses e.g. [\"RECRUITING\"].",
    inputSchema: { type: "object", properties: {
      sponsor: { type: "string" }, condition: { type: "string" }, intervention: { type: "string" },
      phases: { type: "array", items: { type: "string" } }, statuses: { type: "array", items: { type: "string" } },
      max_records: { type: "integer", default: 20, maximum: 100 },
      include_global: { type: "boolean", default: false, description: INCLUDE_GLOBAL_DESC },
      global_sources: { type: "array", items: { type: "string", enum: GLOBAL_SOURCES }, description: GLOBAL_SOURCES_DESC } } },
    async run(a) {
      const srcs = a.include_global === true ? parseSources(a.global_sources) : null;
      const q = new URLSearchParams({ format: "json", sort: "LastUpdatePostDate:desc", pageSize: String(clamp(a.max_records, 100, 20)) });
      if (a.sponsor) q.set("query.spons", a.sponsor);
      if (a.condition) q.set("query.cond", a.condition);
      if (a.intervention) q.set("query.intr", a.intervention);
      if (a.statuses?.length) q.set("filter.overallStatus", a.statuses.join(","));
      if (a.phases?.length) q.set("filter.advanced", a.phases.map(p => `AREA[Phase]${p}`).join(" OR "));
      const d = await getJSON(`https://clinicaltrials.gov/api/v2/studies?${q}`);
      if (a.include_global !== true) return (d?.studies || []).map(trialRow);
      const trials = (d?.studies || []).map(s => ({ ...trialRow(s), global_links: registryLinks(s, srcs) }));
      const out = { trials, global_note: "Phase 1: link-outs only; foreign registry records are not ingested." };
      if (trials.some(t => t.global_links.length)) out.global_disclaimer = GLOBAL_DISCLAIMER;
      return out;
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
    description: "Search PubMed, Europe PMC and preprints. Set `include_global: true` to flag papers from studies run outside US/EU oversight (`jurisdiction_flag`). Off by default. (Hosted endpoint: PubMed via NCBI E-utilities; affiliation countries for flags from Europe PMC metadata; \"unknown\" when no country is found, never guessed.) Citation metadata and links only. When showing flagged papers to a user, keep the label and global_disclaimer.",
    inputSchema: { type: "object", properties: { keyword: { type: "string" }, max_records: { type: "integer", default: 10, maximum: 50 },
      include_global: { type: "boolean", default: false, description: INCLUDE_GLOBAL_DESC },
      global_sources: { type: "array", items: { type: "string", enum: GLOBAL_SOURCES }, description: GLOBAL_SOURCES_DESC } }, required: ["keyword"] },
    async run(a) {
      const e = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils";
      const s = await getJSON(`${e}/esearch.fcgi?db=pubmed&retmode=json&sort=pub_date&tool=biocatalystfeed&email=contact@biocat.ai&retmax=${clamp(a.max_records, 50, 10)}&term=${encodeURIComponent(a.keyword)}`);
      const ids = s?.esearchresult?.idlist || [];
      if (!ids.length) return [];
      const m = await getJSON(`${e}/esummary.fcgi?db=pubmed&retmode=json&tool=biocatalystfeed&email=contact@biocat.ai&id=${ids.join(",")}`);
      const rows = ids.map(id => m.result[id]).filter(Boolean).map(r => ({ pmid: r.uid, title: r.title, journal: r.fulljournalname, pubdate: r.pubdate, url: `https://pubmed.ncbi.nlm.nih.gov/${r.uid}/` }));
      if (a.include_global !== true) return rows;
      parseSources(a.global_sources);
      let affs = {}, error;
      try { affs = await epmcAffiliations(rows.map(r => r.pmid)); } catch (e) { error = String(e.message || e); }
      for (const r of rows) {
        const [flag, cs] = paperFlag(affs[r.pmid]);
        r.jurisdiction_flag = flag; r.jurisdiction = cs;
        if (flag === PAPER_FLAG) r.registry_class = REGISTRY_CLASS;
      }
      const out = { papers: rows };
      if (error) out.errors = { global_affiliations: error };
      if (rows.some(r => r.jurisdiction_flag === PAPER_FLAG)) out.global_disclaimer = GLOBAL_DISCLAIMER;
      return out;
    } },
  fda_adcom_meetings: {
    description: "FDA advisory committee meeting notices from the Federal Register.",
    inputSchema: { type: "object", properties: { since: { type: "string", description: "YYYY-MM-DD" }, max_results: { type: "integer", default: 20, maximum: 100 } } },
    async run(a) {
      const q = new URLSearchParams({ "conditions[agencies][]": "food-and-drug-administration", "conditions[type][]": "NOTICE",
        "conditions[term]": "\"advisory committee\" \"notice of meeting\"", per_page: "100", order: "newest" });
      if (a.since && /^\d{4}-\d{2}-\d{2}$/.test(a.since)) q.set("conditions[publication_date][gte]", a.since);
      const d = await getJSON(`https://www.federalregister.gov/api/v1/documents.json?${q}`);
      return (d?.results || []).filter(r => /advisory committee/i.test(r.title) && /notice of (public )?meeting/i.test(r.title)).slice(0, clamp(a.max_results, 100, 20)).map(r => ({ title: r.title, publication_date: r.publication_date, document_number: r.document_number, url: r.html_url }));
    } },
};

const json = (body, status = 200, extra = {}) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "access-control-allow-origin": "*", "access-control-expose-headers": "retry-after, x-ratelimit-limit, x-ratelimit-remaining", "x-content-type-options": "nosniff", "cache-control": "no-store", ...extra } });
const rpcErr = (id, code, message) => ({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });

async function handleRpc(msg) {
  const { id, method, params = {} } = msg || {};
  if (id === undefined) return null; // notification
  switch (method) {
    case "initialize":
      return { jsonrpc: "2.0", id, result: { protocolVersion: PROTOCOL, capabilities: { tools: { listChanged: false } },
        serverInfo: { name: "biocatalystfeed-hosted", version: "0.3.2" },
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
