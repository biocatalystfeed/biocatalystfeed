// BioCatalystFeed hosted MCP endpoint: stateless MCP over Streamable HTTP (JSON responses), per-IP rate limited.
// Built-in read-only tools call public APIs directly (ClinicalTrials.gov, openFDA, PubMed, Federal Register).
// No request bodies or query arguments are logged; Cloudflare's platform may keep standard request logs.
import { DurableObject } from "cloudflare:workers";
const RATE_LIMIT = 30, RATE_WINDOW_MS = 60_000;
// Daily quota (UTC day) in "tool calls". Overridable via [vars] DAILY_LIMIT_ANON; key tiers via the optional API_KEYS KV.
const DAILY_LIMIT_ANON = 200, DAY_MS = 86_400_000;
const utcDay = (t) => new Date(t).toISOString().slice(0, 10);

// One instance per client (idFromName("ip:"+ip) or "key:"+sha256(key)); single-threaded, so counters are exact.
// Stores only {minute window start, count} and {UTC day, tool calls}; an alarm deletes everything after the day ends.
export class IpRateLimiter extends DurableObject {
  async hit(units = 0, dailyLimit = DAILY_LIMIT_ANON) {
    const now = Date.now(), day = utcDay(now);
    let w = (await this.ctx.storage.get("w")) || { start: now, n: 0 };
    if (now - w.start >= RATE_WINDOW_MS) w = { start: now, n: 0 };
    let d = (await this.ctx.storage.get("d")) || { day, n: 0 };
    if (d.day !== day) d = { day, n: 0 };
    w.n++;
    const minuteOk = w.n <= RATE_LIMIT;
    const dailyOk = d.n + units <= dailyLimit;
    if (minuteOk && dailyOk) d.n += units; // rejected requests do not burn daily quota
    await this.ctx.storage.put({ w, d });
    const resetAt = Date.parse(day + "T00:00:00Z") + DAY_MS;
    if (!(await this.ctx.storage.getAlarm())) await this.ctx.storage.setAlarm(resetAt + 1000);
    return { ok: minuteOk && dailyOk, reason: !minuteOk ? "minute" : !dailyOk ? "daily" : null,
      remaining: Math.max(0, RATE_LIMIT - w.n), retryAfter: Math.ceil((w.start + RATE_WINDOW_MS - now) / 1000),
      dailyLimit, dailyUsed: d.n, dailyRemaining: Math.max(0, dailyLimit - d.n), dailyReset: Math.ceil((resetAt - now) / 1000), resetAt };
  }
  async alarm() {
    const d = await this.ctx.storage.get("d");
    if (d && d.day === utcDay(Date.now())) { await this.ctx.storage.setAlarm(Date.parse(d.day + "T00:00:00Z") + DAY_MS + 1000); return; }
    await this.ctx.storage.deleteAll();
  }
}

// Future API keys: header "x-api-key: <k>" or "Authorization: Bearer <k>". Keys are looked up by SHA-256 hash in an
// optional KV binding API_KEYS (value JSON: {"tier":"pro","daily":5000}); raw keys are never stored. Unknown key -> 401.
async function resolveClient(req, env) {
  const auth = req.headers.get("authorization") || "";
  const key = req.headers.get("x-api-key") || (/^Bearer\s+(.+)$/i.exec(auth) || [])[1];
  const anonDaily = Number(env.DAILY_LIMIT_ANON) > 0 ? Number(env.DAILY_LIMIT_ANON) : DAILY_LIMIT_ANON;
  if (!key) return { id: "ip:" + (req.headers.get("cf-connecting-ip") || "unknown"), tier: "free", daily: anonDaily };
  if (!env.API_KEYS) return { error: "API keys are not enabled yet; remove the key header to use the free tier" };
  const h = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(key.trim())))].map(b => b.toString(16).padStart(2, "0")).join("");
  const rec = await env.API_KEYS.get(h, "json");
  if (!rec) return { error: "invalid API key" };
  return { id: "key:" + h, tier: rec.tier || "pro", daily: Number(rec.daily) > 0 ? Number(rec.daily) : 5000 };
}
const toolUnits = (b) => (Array.isArray(b) ? b.slice(0, 10) : [b]).filter(m => m && m.method === "tools/call").length;
const UPGRADE = "Higher limits via API keys are coming; contact contact@biocat.ai, or self-host for free: pip install biocatalystfeed";

const PROTOCOL = "2025-06-18";
const UA = "BioCatalystFeed-hosted/0.4.0 (+https://github.com/biocatalystfeed/biocatalystfeed; contact@biocat.ai)";
const SEC_UA = "BioCatalystFeed contact@biocat.ai"; // SEC fair-access policy: "Company Name email" format
const clamp = (n, hi, d) => Math.max(1, Math.min(Number.isFinite(+n) ? Math.floor(+n) : d, hi));

async function getJSON(url) {
  let r;
  try { r = await fetch(url, { headers: { "user-agent": /sec\.gov\//.test(url) ? SEC_UA : UA, accept: "application/json" }, signal: AbortSignal.timeout(15000) }); }
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
const GLOBAL_SOURCES = ["chictr", "ictrp"];
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

// ---- FDA complete response letters (openFDA /transparency/crl.json). Source: U.S. FDA via openFDA; public domain (CC0).
// Read-only search; personal fields in the source (company representative, signatory, address) are not returned.
const CRL_SOURCE = "U.S. Food and Drug Administration, openFDA complete response letters (open.fda.gov); public domain";
const CRL_TOPIC_RULES = [
  ["human_factors", ["HUMAN FACTORS"]], ["clinical_pharmacology", ["CLINICAL PHARMACOLOGY", "BIOPHARMACEUTIC", "BIOEQUIVALENCE"]],
  ["nonclinical", ["NONCLINICAL", "TOXICOLOGY", "PHARMACOLOGY/TOXICOLOGY"]], ["facility", ["FACILITY", "FACILITIES", "INSPECTION"]],
  ["product_quality", ["PRODUCT QUALITY", "CHEMISTRY", "MANUFACTURING", "CMC", "MICROBIOLOGY", "DRUG PRODUCT", "DRUG SUBSTANCE", "DEVICE", "COMBINATION PRODUCT", "PROCESS"]],
  ["clinical", ["CLINICAL", "STATISTIC", "BIOSTATISTIC", "EFFICACY"]], ["safety", ["RISK EVALUATION AND MITIGATION", "SAFETY"]],
];
const CRL_BOILER = ["SAFETY UPDATE", "PRESCRIBING INFORMATION", "CARTON AND CONTAINER", "PROPRIETARY NAME", "MEDICATION GUIDE", "ADDITIONAL COMMENT", "OTHER", "LABELING", "COMPLETE RESPONSE", "ADMINISTRATION", "REQUIRED PEDIATRIC", "POSTMARKETING", "SUBMISSION OF REMS", "PDUFA", "RECOMMENDATION", "RECOM MENDATION", "PATH FORWARD", "TENTATIVE APPROVAL", "REGULATORY", "CENTER FOR DEVICES"];
function crlTopics(text) {
  const out = [];
  for (const m of String(text || "").matchAll(/^[ \t]*([A-Z][A-Z ,\/&()\-]{3,70})[ \t]*$/gm)) {
    const h = m[1].replace(/\s+/g, " ").trim();
    if (CRL_BOILER.some(b => h === b || h.startsWith(b))) continue;
    const t = CRL_TOPIC_RULES.find(([, n]) => n.some(x => h.includes(x)))?.[0];
    if (t && !(t === "safety" && h.includes("SAFETY UPDATE")) && !out.includes(t)) out.push(t);
  }
  return out;
}
const crlIso = d => { const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(String(d || "").trim()); return m ? `${m[3]}-${m[1]}-${m[2]}` : (d || null); };
const ymd = (d, dflt) => (/^\d{4}-\d{2}-\d{2}$/.test(d || "") ? d.replace(/-/g, "") : dflt);

// Sponsor aliases (mirror of fdawatch/aliases.py ct_queries): names/tickers -> the string ClinicalTrials.gov actually uses.
const CT_SPONSOR = { "tern": "Terns, Inc.", "terns": "Terns, Inc.", "terns pharmaceuticals": "Terns, Inc.", "terns inc": "Terns, Inc.",
  "lly": "Eli Lilly and Company", "vktx": "Viking Therapeutics", "mdgl": "Madrigal Pharmaceuticals", "nvo": "Novo Nordisk A/S",
  "gpcr": "Structure Therapeutics", "alt": "Altimmune" };
const ctSponsor = s => CT_SPONSOR[String(s).toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim()] || s;

const TICKER_ALIASES = {"viking":["VKTX","Viking Therapeutics"],"eli lilly":["LLY","Eli Lilly"],"lilly":["LLY","Eli Lilly"],"madrigal":["MDGL","Madrigal Pharmaceuticals"],"terns":["TERN","Terns Pharmaceuticals"],"novo nordisk":["NVO","Novo Nordisk"],"novo":["NVO","Novo Nordisk"],"zealand pharma":["ZEAL.CO","Zealand Pharma"],"zealand":["ZEAL.CO","Zealand Pharma"],"structure":["GPCR","Structure Therapeutics"],"altimmune":["ALT","Altimmune"]}; // generated from fdawatch/aliases.py (normalized name -> [ticker, company])

// ---- Provenance + ticker confidence (mirrors biowatch/provenance.py). verify_hash = sha256 of the record's canonical
// JSON (sorted keys) without verified_as_of / verify_hash / source_url / retrieved / ticker_* fields.
const PROV = new Set(["verified_as_of", "verify_hash", "source_url", "retrieved"]);
const canon = v => Array.isArray(v) ? `[${v.map(canon).join(",")}]` : v && typeof v === "object"
  ? `{${Object.keys(v).filter(k => v[k] !== undefined).sort().map(k => `${JSON.stringify(k)}:${canon(v[k])}`).join(",")}}` : JSON.stringify(v ?? null);
async function sha(s) { const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)); return "sha256:" + [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join(""); }
async function stamp(r, asOf) {
  const body = {}; for (const [k, v] of Object.entries(r)) if (!PROV.has(k) && !k.startsWith("ticker_")) body[k] = v;
  if (body.provenance && typeof body.provenance === "object") body.provenance = Object.fromEntries(Object.entries(body.provenance).filter(([k]) => !PROV.has(k)));
  r.verified_as_of = asOf; r.source_url = r.source_url || r.url || null; r.verify_hash = await sha(canon(body)); return r;
}
const normName = s => String(s || "").toLowerCase().replace(/[^a-z0-9 ]/g, " ")
  .replace(/\b(inc|corp|corporation|co|ltd|plc|a s|ag|sa|llc|company|and|pharmaceuticals?|therapeutics|biosciences?|biotherapeutics|biopharma(ceuticals)?|holdings|group|international|incorporated|limited|gmbh|s a|n v|k k)\b/g, " ").replace(/\s+/g, " ").trim();
let SEC_NAMES = null;
async function secNames() {
  if (SEC_NAMES) return SEC_NAMES;
  const req = new Request("https://www.sec.gov/files/company_tickers.json"), cache = caches.default;
  let r = await cache.match(req);
  if (!r) { const f = await fetch(req, { headers: { "user-agent": SEC_UA }, signal: AbortSignal.timeout(15000) }); if (!f.ok) return {}; r = new Response(await f.text(), { headers: { "cache-control": "max-age=86400" } }); await cache.put(req, r.clone()); }
  const d = await r.json(); SEC_NAMES = {};
  for (const v of Object.values(d)) { const k = normName(v.title); if (!(k in SEC_NAMES)) SEC_NAMES[k] = [v.ticker, v.title]; }
  return SEC_NAMES;
}
function tickerMatch(name, names, srcTicker) {
  if (srcTicker) return { ticker: srcTicker, ticker_confidence: 1.0, ticker_method: "source", ticker_company: name };
  const none = { ticker: null, ticker_confidence: 0, ticker_method: "none", ticker_company: null }, n = normName(name);
  if (!n) return none;
  if (TICKER_ALIASES[n]) return { ticker: TICKER_ALIASES[n][0], ticker_confidence: 0.95, ticker_method: "alias_table", ticker_company: TICKER_ALIASES[n][1] };
  if (/\b(kgaa|darmstadt)\b/.test(n) || !names) return none;
  if (names[n]) return { ticker: names[n][0], ticker_confidence: 0.9, ticker_method: "sec_exact_name", ticker_company: names[n][1] };
  const f = n.split(" ")[0];
  if (n.length >= 4 && f.length >= 4) for (const [k, v] of Object.entries(names)) if (k.split(" ")[0] === f && (k.startsWith(n) || n.startsWith(k))) return { ticker: v[0], ticker_confidence: 0.6, ticker_method: "sec_prefix_name", ticker_company: v[1] };
  return none;
}
async function enrich(out, useSec = true) {
  const asOf = new Date().toISOString().replace(/\.\d+Z$/, "Z");
  let names = null; if (useSec) try { names = await secNames(); } catch { names = null; }
  const one = async r => {
    if (!r || typeof r !== "object" || Array.isArray(r) || r.verify_hash || !("url" in r || "key" in r || "nct_id" in r)) return;
    const nm = r.sponsor || r.company || r.lead_sponsor;
    if (nm && !("ticker_confidence" in r)) { const t = tickerMatch(nm, names, r.ticker); Object.assign(r, t, r.ticker ? { ticker: r.ticker } : {}); }
    await stamp(r, asOf);
  };
  if (Array.isArray(out)) for (const r of out) await one(r);
  else if (out && typeof out === "object") { const ls = Object.values(out).filter(v => Array.isArray(v) && v.length && typeof v[0] === "object"); for (const l of ls) for (const r of l) await one(r); if (!ls.length) await one(out); }
  return out;
}

// ---- Trial readout calendar + Trials at Risk (mirror readoutwatch/, lighter: no local history, so no delayed /
// enrollment flags on the hosted endpoint).
const ACTIVE = "NOT_YET_RECRUITING,RECRUITING,ENROLLING_BY_INVITATION,ACTIVE_NOT_RECRUITING";
const isoDay = (n = 0) => new Date(Date.now() + n * 864e5).toISOString().slice(0, 10);
async function ctReadouts(a, statuses, field, lo, hi, n) {
  const q = new URLSearchParams({ format: "json", sort: `${field}:asc`, pageSize: String(n),
    fields: "NCTId,BriefTitle,OverallStatus,WhyStopped,Phase,LeadSponsorName,Condition,EnrollmentCount,EnrollmentType,PrimaryCompletionDate,PrimaryCompletionDateType,CompletionDate,LastUpdatePostDate" });
  q.set("filter.overallStatus", statuses);
  if (a.sponsor) q.set("query.spons", ctSponsor(a.sponsor));
  if (a.condition) q.set("query.cond", a.condition);
  if (a.intervention) q.set("query.intr", a.intervention);
  const ph = Array.isArray(a.phases) ? (a.phases.includes("any") ? [] : a.phases) : ["PHASE2", "PHASE3"];
  const adv = [`AREA[${field}]RANGE[${lo},${hi}]`];
  if (ph.length) adv.push("(" + ph.map(p => `AREA[Phase]${String(p).toUpperCase()}`).join(" OR ") + ")");
  if (a.industry_only !== false) adv.push("AREA[LeadSponsorClass]INDUSTRY");
  q.set("filter.advanced", adv.join(" AND "));
  const d = await getJSON(`https://clinicaltrials.gov/api/v2/studies?${q}`);
  return (d?.studies || []).map(s => {
    const p = s.protocolSection || {}, st = p.statusModule || {}, de = p.designModule || {}, id = p.identificationModule || {};
    const dt = st.primaryCompletionDateStruct?.date || null, typ = st.primaryCompletionDateStruct?.type || null;
    return { key: `readout:${id.nctId}`, kind: "readout", nct_id: id.nctId, title: id.briefTitle, readout_date: dt,
      date_precision: dt ? (dt.length === 10 ? "day" : "month") : null, readout_date_type: typ, completion_date: st.completionDateStruct?.date || null,
      status: st.overallStatus, phase: (de.phases || []).join("/") || null, sponsor: p.sponsorCollaboratorsModule?.leadSponsor?.name || null,
      conditions: (p.conditionsModule?.conditions || []).join("; ") || null, enrollment: de.enrollmentInfo?.count ?? null,
      enrollment_type: de.enrollmentInfo?.type || null, why_stopped: st.whyStopped || null, last_update_posted: st.lastUpdatePostDateStruct?.date || null,
      url: `https://clinicaltrials.gov/study/${id.nctId}`, source_url: `https://clinicaltrials.gov/api/v2/studies/${id.nctId}`,
      provenance: { source: "ClinicalTrials.gov API v2 (NLM; public data)", field: "statusModule.primaryCompletionDateStruct", method: "official registry record (sponsor-reported)" } };
  });
}
async function readoutCalendar(a) {
  const re = /^\d{4}-\d{2}-\d{2}$/;
  let lo = re.test(a.since || "") ? a.since : isoDay(0), hi = re.test(a.until || "") ? a.until : null;
  if (a.upcoming_days != null || !hi) { if (a.upcoming_days != null || !re.test(a.since || "")) lo = isoDay(0); hi = hi && a.upcoming_days == null ? hi : isoDay(Math.max(0, Math.min(+a.upcoming_days || 90, 1095))); }
  let rows = await enrich(await ctReadouts(a, ACTIVE, "PrimaryCompletionDate", lo, hi, clamp(a.max_results, 1000, 100)), a._sec !== false);
  if (a.ticker_only) rows = rows.filter(r => r.ticker);
  return { window: [lo, hi], readouts: rows };
}

// ---- FDA decision calendar (mirrors decisionwatch/core.py, lighter). pdufa = company-disclosed in SEC 8-K text
// (EDGAR full-text search; UNVERIFIED regex extraction), adcom = Federal Register notices, approval = Drugs@FDA,
// crl = openFDA. Every event carries confidence + provenance. Not investment advice.
const MON = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
const DEC_CONF = { pdufa: "company-disclosed", adcom: "scheduled", approval: "confirmed", crl: "confirmed" };
const pad = n => String(n).padStart(2, "0");
function parseWhen(t, fileDate) {
  t = String(t || "").toLowerCase().replace(/\./g, "").trim();
  let m = /^([a-z]{3})[a-z]*\s+(\d{1,2}),?\s+(20\d\d)$/.exec(t); if (m && MON[m[1]]) return [`${m[3]}-${pad(MON[m[1]])}-${pad(m[2])}`, "day"];
  m = /^([a-z]{3})[a-z]*\s+(\d{1,2})$/.exec(t);
  if (m && MON[m[1]] && fileDate) { let y = +fileDate.slice(0, 4); let d = `${y}-${pad(MON[m[1]])}-${pad(m[2])}`; if (d < fileDate) d = `${y + 1}${d.slice(4)}`; return [d, "day"]; }
  m = /^([a-z]{3})[a-z]*\s+(20\d\d)$/.exec(t); if (m && MON[m[1]]) return [`${m[2]}-${pad(MON[m[1]])}-01`, "month"];
  const Q = { first: 1, second: 2, third: 3, fourth: 4 };
  m = /(first|second|third|fourth)\s+quarter\s+(?:of\s+)?(20\d\d)/.exec(t) || /q([1-4])\s*(20\d\d)/.exec(t);
  if (m) return [`${m[2]}-${pad(((Q[m[1]] || +m[1]) - 1) * 3 + 1)}-01`, "quarter"];
  return [null, null];
}
const DATE_SRC = "((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\\.?\\s+\\d{1,2}(?:,?\\s+20\\d\\d)?|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\\s+20\\d\\d|(?:first|second|third|fourth)\\s+quarter\\s+(?:of\\s+)?20\\d\\d|q[1-4]\\s*20\\d\\d)";
function pdufaDates(text) {
  const out = [], re = /PDUFA|target action date|goal date/gi; let m;
  while ((m = re.exec(text))) {
    const seg = text.slice(m.index, m.index + 200), d = new RegExp(DATE_SRC, "i").exec(seg);
    if (d && d.index < 140) out.push({ date_text: d[1].replace(/\s+/g, " "), context: text.slice(Math.max(0, m.index - 150), m.index + 220) });
  }
  return out;
}
const drugIn = ctx => (/\b([a-z]{4,}(?:mab|nib|tide|stat|parin|cel|gene|vec|lisib|tinib|ciclib|vir|sartan|gliflozin|glutide|siran|rsen|cept|xaban|sentan|platin))\b/.exec(ctx || "") || [])[1] || null;
const hit = (hay, term) => !term || String(hay || "").toLowerCase().includes(String(term).toLowerCase());
async function secText(url) {
  const r = await fetch(url, { headers: { "user-agent": SEC_UA }, signal: AbortSignal.timeout(15000) });
  if (!r.ok) throw new Error(`sec.gov HTTP ${r.status}`);
  return (await r.text()).replace(/<(script|style)[\s\S]*?<\/\1>/gi, " ").replace(/<[^>]+>/g, " ").replace(/&nbsp;|&#160;/g, " ").replace(/&amp;/g, "&").replace(/\s+/g, " ");
}
async function decPdufa(a, today) {
  const q = `"PDUFA"${a.drug ? ` "${String(a.drug).replace(/"/g, "")}"` : ""}${a.condition ? ` "${String(a.condition).replace(/"/g, "")}"` : ""}`;
  const since = new Date(Date.parse(today) - 365 * 864e5).toISOString().slice(0, 10);
  const p = new URLSearchParams({ q, forms: "8-K", dateRange: "custom", startdt: since, enddt: today });
  const d = await getJSON(`https://efts.sec.gov/LATEST/search-index?${p}`);
  let hits = (d?.hits?.hits || []).sort((x, y) => (y._source.file_date || "").localeCompare(x._source.file_date || ""));
  if (a.company) hits = hits.filter(h => hit((h._source.display_names || []).join(" "), a.company));
  const out = new Map();
  for (const h of hits.slice(0, clamp(a.max_docs, 10, 6))) {
    const s = h._source, [adsh, fn] = h._id.split(":"), cik = String(+s.ciks[0]);
    const url = `https://www.sec.gov/Archives/edgar/data/${cik}/${adsh.replace(/-/g, "")}/${fn}`;
    const dn = (s.display_names || [""])[0], tk = /\(([A-Z.\-]{1,6})(?:,\s*[A-Z.\-]{1,6})*\)\s*\(CIK/.exec(dn);
    let text; try { text = await secText(url); } catch { continue; }
    for (const c of pdufaDates(text).slice(0, 3)) {
      const [date, prec] = parseWhen(c.date_text, s.file_date); if (!date) continue;
      const drug = drugIn(c.context) || a.drug || null, company = dn.replace(/\s*\(.*$/, "").trim();
      const key = `pdufa:${cik}:${(drug || "unknown").toLowerCase()}`;
      if (out.has(key)) continue;
      out.set(key, { key, kind: "pdufa", date, date_precision: prec, confidence: DEC_CONF.pdufa, status: date >= today ? "pending" : "date_passed",
        company, ticker: tk ? tk[1] : null, drug, title: `PDUFA ${c.date_text} - ${company}${drug ? ` (${drug})` : ""}`, url,
        date_text: c.date_text, context: c.context.slice(0, 400),
        provenance: { source: "SEC EDGAR full-text search (company 8-K filings)", field: "8-K text near 'PDUFA' / 'target action date'", method: "regex extraction (UNVERIFIED) - read the filing", filed: s.file_date } });
    }
  }
  return [...out.values()];
}
async function decAdcom(a, today) {
  const q = new URLSearchParams({ "conditions[agencies][]": "food-and-drug-administration", "conditions[type][]": "NOTICE",
    "conditions[term]": "\"advisory committee\"", per_page: "100", order: "newest", "conditions[publication_date][gte]": new Date(Date.parse(today) - 365 * 864e5).toISOString().slice(0, 10) });
  for (const f of ["title", "abstract", "dates", "publication_date", "html_url", "document_number"]) q.append("fields[]", f);
  const d = await getJSON(`https://www.federalregister.gov/api/v1/documents.json?${q}`);
  const out = [];
  for (const r of d?.results || []) {
    if (!/advisory committee|panel/i.test(r.title) || !/notice of (public )?meeting|postpone|cancel/i.test(`${r.title} ${r.abstract || ""}`)) continue;
    const hay = `${r.title} ${r.abstract || ""}`;
    if (!hit(hay, a.drug) || !hit(hay, a.company) || !hit(hay, a.condition)) continue;
    const m = new RegExp("(January|February|March|April|May|June|July|August|September|October|November|December)\\s+(\\d{1,2}),\\s+(20\\d\\d)").exec(r.dates || "");
    const date = m ? `${m[3]}-${pad(MON[m[1].slice(0, 3).toLowerCase()])}-${pad(m[2])}` : null;
    const status = /cancel/i.test(r.title) ? "cancelled" : /postpone/i.test(r.title) ? "postponed" : (date && date < today ? "held" : "scheduled");
    out.push({ key: `adcom:${r.document_number}`, kind: "adcom", date, date_precision: date ? "day" : null, confidence: DEC_CONF.adcom, status,
      company: null, ticker: null, drug: a.drug || null, title: `AdCom ${date || "?"}: ${r.title.split(";")[0]}`, url: r.html_url,
      provenance: { source: "Federal Register (FDA notices)", field: "dates", method: "parsed from the official notice", published: r.publication_date } });
  }
  return out;
}
async function decApprovals(a, today, since) {
  const t = encodeURIComponent(String(a.drug || a.company || "").replace(/["\\]/g, "")).replace(/%20/g, "+");
  if (!t) return [];
  const search = a.drug ? `(openfda.generic_name:"${t}"+OR+openfda.brand_name:"${t}"+OR+products.brand_name:"${t}")` : `sponsor_name:"${t.toUpperCase()}"`;
  const d = await getJSON(`https://api.fda.gov/drug/drugsfda.json?search=${search}&limit=100`);
  const out = [];
  for (const r of d?.results || []) for (const x of r.submissions || []) {
    const dt = /^\d{8}$/.test(x.submission_status_date || "") ? `${x.submission_status_date.slice(0, 4)}-${x.submission_status_date.slice(4, 6)}-${x.submission_status_date.slice(6)}` : null;
    if (x.submission_status !== "AP" || !dt || dt < since) continue;
    if (!(x.submission_type === "ORIG" || /EFFIC/i.test(x.submission_class_code_description || ""))) continue;
    const brands = [...new Set((r.products || []).map(p => p.brand_name))].join("; ");
    out.push({ key: `approval:${r.application_number}:${x.submission_type}${x.submission_number}`, kind: "approval", date: dt, date_precision: "day", confidence: DEC_CONF.approval, status: "approved",
      company: r.sponsor_name, ticker: null, drug: brands, title: `Approved ${dt}: ${brands} (${r.application_number} ${x.submission_type}${x.submission_number})`,
      url: `https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo=${r.application_number.replace(/\D/g, "")}`,
      provenance: { source: "Drugs@FDA via openFDA (public domain)", field: "submissions.submission_status_date", method: "official record" } });
  }
  return out;
}

const TOOLS = {
  search_trials: {
    description: "Search clinical trials (ClinicalTrials.gov by default). Set `include_global: true` to also include links to records in non-FDA/EMA registries (China's ChiCTR, other WHO-listed national registries). Global results carry `registry_class: \"non-FDA/EMA registry\"` and a `global_disclaimer`. Off by default. Links (registry ID + URL from ClinicalTrials.gov secondary IDs) are in each trial's global_links. When showing global results to a user, keep the label and the disclaimer. Most recently updated first; phases e.g. [\"PHASE2\",\"PHASE3\"]; statuses e.g. [\"RECRUITING\"].",
    inputSchema: { type: "object", properties: {
      sponsor: { type: "string", description: "Sponsor/company name, free text (ClinicalTrials.gov query.spons). Known tickers/names are alias-resolved, e.g. 'TERN' -> 'Terns, Inc.'." },
      condition: { type: "string", description: "Condition or disease, free text (e.g. 'obesity')." },
      intervention: { type: "string", description: "Drug or intervention name, free text (e.g. 'semaglutide')." },
      phases: { type: "array", items: { type: "string", enum: ["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"] }, description: "Trial phases to keep." },
      statuses: { type: "array", items: { type: "string" }, description: "Overall statuses to keep, e.g. RECRUITING, ACTIVE_NOT_RECRUITING, COMPLETED, TERMINATED." },
      max_records: { type: "integer", default: 20, maximum: 100, description: "Maximum trials to return (1-100)." },
      include_global: { type: "boolean", default: false, description: INCLUDE_GLOBAL_DESC },
      global_sources: { type: "array", items: { type: "string", enum: GLOBAL_SOURCES }, description: GLOBAL_SOURCES_DESC } } },
    async run(a) {
      const srcs = a.include_global === true ? parseSources(a.global_sources) : null;
      const q = new URLSearchParams({ format: "json", sort: "LastUpdatePostDate:desc", pageSize: String(clamp(a.max_records, 100, 20)) });
      if (a.sponsor) q.set("query.spons", ctSponsor(a.sponsor));
      if (a.condition) q.set("query.cond", a.condition);
      if (a.intervention) q.set("query.intr", a.intervention);
      if (a.statuses?.length) q.set("filter.overallStatus", a.statuses.join(","));
      if (a.phases?.length) q.set("filter.advanced", a.phases.map(p => `AREA[Phase]${p}`).join(" OR "));
      const d = await getJSON(`https://clinicaltrials.gov/api/v2/studies?${q}`);
      if (a.include_global !== true) return (d?.studies || []).map(trialRow);
      const trials = (d?.studies || []).map(s => ({ ...trialRow(s), global_links: registryLinks(s, srcs) }));
      const out = { trials };
      if (trials.some(t => t.global_links.length)) out.global_disclaimer = GLOBAL_DISCLAIMER;
      return out;
    } },
  get_trial: {
    description: "Get one trial record from ClinicalTrials.gov by NCT ID.",
    inputSchema: { type: "object", properties: { nct_id: { type: "string", description: "ClinicalTrials.gov ID: 'NCT' followed by 8 digits, e.g. NCT04184622." } }, required: ["nct_id"] },
    async run(a) {
      if (!/^NCT\d{8}$/i.test(a.nct_id || "")) throw new Error("nct_id must look like NCT01234567");
      const d = await getJSON(`https://clinicaltrials.gov/api/v2/studies/${a.nct_id.toUpperCase()}?format=json`);
      if (!d) throw new Error("trial not found");
      return trialRow(d);
    } },
  fda_approvals: {
    description: "Drugs@FDA submissions from openFDA (Data provided by the U.S. FDA). Filter by sponsor name.",
    inputSchema: { type: "object", properties: { sponsor: { type: "string", description: "Drugs@FDA sponsor_name as openFDA stores it (upper-case abbreviation, e.g. 'LILLY', 'MADRIGAL')." }, max_results: { type: "integer", default: 20, maximum: 100, description: "Maximum applications to return (1-100)." } },
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
    inputSchema: { type: "object", properties: { keyword: { type: "string", description: "PubMed query syntax, e.g. 'tirzepatide AND obesity' or 'Viking Therapeutics[ad]'." }, max_records: { type: "integer", default: 10, maximum: 50, description: "Maximum papers to return (1-50)." },
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
  fda_complete_response_letters: {
    description: "FDA complete response letters (CRLs) for NDAs/BLAs from openFDA, newest letter first: company, application number(s), letter date, application_status ('Approved' = approved since, 'Unapproved' = not yet), deficiency topics (facility, product_quality, clinical, clinical_pharmacology, nonclinical, safety, human_factors) parsed from the letter's section headings, and the PDF link. since/until filter the letter date (YYYY-MM-DD); application e.g. 'NDA 218705' or '218705'; keyword matches company or any word in the letter. FDA publishes CRLs with a lag and redactions. Source: U.S. FDA / openFDA (public domain). Factual record only; not investment, legal or medical advice.",
    inputSchema: { type: "object", properties: {
      company: { type: "string", description: "Company name phrase as it appears on the letter." },
      application: { type: "string", description: "NDA/BLA number, e.g. 'NDA 218705', 'BLA 761308' or '218705'." },
      since: { type: "string", description: "Letter date from (YYYY-MM-DD)." }, until: { type: "string", description: "Letter date to (YYYY-MM-DD)." },
      status: { type: "string", enum: ["Approved", "Unapproved"], description: "'Approved' = approved since the letter; 'Unapproved' = not yet." },
      keyword: { type: "string", description: "Matches company, application number or any word in the letter text." },
      topic: { type: "string", enum: CRL_TOPIC_RULES.map(([t]) => t), description: "Keep letters with this deficiency topic." },
      max_results: { type: "integer", default: 20, maximum: 100, description: "Maximum letters to return (1-100)." } } },
    async run(a) {
      const parts = [`letter_date:[${ymd(a.since, "19000101")}+TO+${ymd(a.until, "29991231")}]`];
      if (a.company) parts.push(`company_name:"${encodeURIComponent(String(a.company).replace(/["\\]/g, ""))}"`);
      if (a.application) {
        const m = /^(?:(NDA|BLA|BL)\s*)?(\d{6})$/i.exec(String(a.application).trim());
        if (!m) throw new Error("application must look like 'NDA 218705', 'BLA 761308' or '218705'");
        parts.push(`application_number:*${m[2]}*`);
      }
      if (a.status) { if (!["Approved", "Unapproved"].includes(a.status)) throw new Error("status must be Approved or Unapproved"); parts.push(`approval_status:${a.status}`); }
      const want = clamp(a.max_results, 100, 20), local = !!(a.keyword || a.topic);
      const d = await getJSON(`https://api.fda.gov/transparency/crl.json?search=${parts.join("+AND+")}&sort=letter_date:desc&limit=${local ? 1000 : want}`);
      const kw = String(a.keyword || "").toLowerCase(), out = [];
      for (const r of d?.results || []) {
        const apps = (r.application_number || []).map(x => String(x).replace(/\s+/g, " ").trim());
        if (kw && !`${r.company_name || ""} ${apps.join(" ")} ${r.text || ""}`.toLowerCase().includes(kw)) continue;
        const topics = crlTopics(r.text);
        if (a.topic && !topics.includes(a.topic)) continue;
        out.push({ letter_date: crlIso(r.letter_date), letter_type: r.letter_type, company: (r.company_name || "").trim() || null,
          applications: apps.join(", ") || null, application_status: r.approval_status, topics,
          url: r.file_name ? `https://download.open.fda.gov/crl/${r.file_name}` : null, source: CRL_SOURCE });
        if (out.length >= want) break;
      }
      return out;
    } },
  fda_decisions: {
    description: "FDA decision calendar: upcoming and recent FDA decision events, upcoming soonest first, then past newest first. kinds: 'pdufa' = PDUFA / target action dates disclosed by companies in SEC 8-K filings (FDA does not publish them; confidence 'company-disclosed', UNVERIFIED regex extraction - read the linked filing), 'adcom' = FDA advisory committee meetings from Federal Register notices (confidence 'scheduled'; status scheduled/postponed/cancelled/held), 'approval' = original approvals and efficacy supplements from Drugs@FDA (needs drug or company), 'crl' = complete response letters from openFDA. Each event has date, date_precision, confidence, status, company, ticker, drug, title, url (official record) and provenance {source, field, method}. Returns {events, errors}. Hosted endpoint is read-only (no watches); for change notifications use the open-source package's snapshot_fda_decisions. Scheduling/reference data, not investment advice.",
    inputSchema: { type: "object", properties: {
      drug: { type: "string", description: "Drug name or code (e.g. 'tirzepatide'); matched against 8-K text, AdCom notices, Drugs@FDA names and CRL text." },
      company: { type: "string", description: "Company name or ticker (matched against the SEC filer name/ticker, Drugs@FDA sponsor and CRL company)." },
      condition: { type: "string", description: "Condition / disease text (e.g. 'obesity'); matched against 8-K text, AdCom notices and CRL text." },
      kinds: { type: "array", items: { type: "string", enum: ["pdufa", "adcom", "approval", "crl"] }, description: "Event kinds to include (default all)." },
      upcoming_days: { type: "integer", maximum: 730, description: "Only upcoming pdufa/adcom events from today to today+N days." },
      since: { type: "string", description: "Event date from (YYYY-MM-DD); default 365 days ago for past events." },
      max_docs: { type: "integer", default: 6, maximum: 10, description: "Maximum SEC 8-K documents to parse for PDUFA dates (1-10)." },
      max_results: { type: "integer", default: 30, maximum: 100, description: "Maximum events to return (1-100)." } } },
    async run(a) {
      const today = new Date().toISOString().slice(0, 10);
      let kinds = Array.isArray(a.kinds) && a.kinds.length ? a.kinds : ["pdufa", "adcom", "approval", "crl"];
      if (kinds.some(k => !DEC_CONF[k])) throw new Error("kinds must be among pdufa, adcom, approval, crl");
      let since = /^\d{4}-\d{2}-\d{2}$/.test(a.since || "") ? a.since : new Date(Date.parse(today) - 365 * 864e5).toISOString().slice(0, 10), until = "9999";
      if (a.upcoming_days != null) { since = today; until = new Date(Date.parse(today) + Math.max(0, Math.min(+a.upcoming_days || 0, 730)) * 864e5).toISOString().slice(0, 10); kinds = kinds.filter(k => k === "pdufa" || k === "adcom"); }
      const jobs = { pdufa: () => decPdufa(a, today), adcom: () => decAdcom(a, today), approval: () => decApprovals(a, today, since),
        crl: async () => (await TOOLS.fda_complete_response_letters.run({ company: a.company, keyword: a.drug || a.condition, since, max_results: 50 })).map(r => ({
          key: `crl:${r.url}`, kind: "crl", date: r.letter_date, date_precision: "day", confidence: DEC_CONF.crl, status: r.application_status === "Approved" ? "approved_since" : "complete_response",
          company: r.company, ticker: null, drug: a.drug || null, title: `CRL ${r.letter_date}: ${r.company} ${r.applications || ""}`, url: r.url, topics: r.topics,
          provenance: { source: CRL_SOURCE, field: "letter_date", method: "official record (published with a lag)" } })) };
      const errors = [], evs = [];
      await Promise.all(kinds.map(async k => { try { evs.push(...await jobs[k]()); } catch (e) { errors.push({ kind: k, error: String(e.message || e).slice(0, 300) }); } }));
      const inWin = evs.filter(e => (e.date || "") >= since && (e.date || "9999") <= until);
      const up = inWin.filter(e => (e.date || "") >= today).sort((x, y) => x.date.localeCompare(y.date));
      const past = inWin.filter(e => (e.date || "") < today).sort((x, y) => (y.date || "").localeCompare(x.date || ""));
      return { events: [...up, ...past].slice(0, clamp(a.max_results, 100, 30)), errors, disclaimer: "Scheduling/reference data, not investment advice. pdufa dates are company-disclosed and unverified." };
    } },
  readout_calendar: {
    description: "Market-wide clinical trial readout calendar from ClinicalTrials.gov: trials whose PRIMARY COMPLETION DATE (last participant examined for the primary outcome; top-line data usually follow weeks to months later) falls in the window, soonest first. Default: active, industry-sponsored PHASE2/PHASE3 trials, next 90 days. Each record: nct_id, title, readout_date, date_precision, readout_date_type (ESTIMATED = anticipated, often slips; ACTUAL), status, phase, sponsor, ticker, ticker_confidence (0-1), ticker_method, conditions, enrollment, url, and provenance verified_as_of, verify_hash, source_url. Returns {window, readouts}. Hosted endpoint is read-only; for slip/new-readout alerts use the open-source package's snapshot_readouts. Not investment advice.",
    inputSchema: { type: "object", properties: {
      sponsor: { type: "string", description: "Lead sponsor name or ticker (known tickers alias-resolved, e.g. 'VKTX')." },
      condition: { type: "string", description: "Condition or disease, free text (e.g. 'obesity')." },
      intervention: { type: "string", description: "Drug or intervention, free text." },
      phases: { type: "array", items: { type: "string", enum: ["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA", "any"] }, description: "Phases to keep (default PHASE2, PHASE3); [\"any\"] for all." },
      since: { type: "string", description: "Readout (primary completion) date from (YYYY-MM-DD)." },
      until: { type: "string", description: "Readout date to (YYYY-MM-DD)." },
      upcoming_days: { type: "integer", maximum: 1095, description: "Readouts from today to today+N days (default 90 when since/until are omitted)." },
      industry_only: { type: "boolean", default: true, description: "Only industry lead sponsors (default true); false adds academic/NIH/other." },
      ticker_only: { type: "boolean", default: false, description: "Only trials whose sponsor matched a stock ticker." },
      max_results: { type: "integer", default: 100, maximum: 1000, description: "Maximum readouts to return (1-1000)." } } },
    run: a => readoutCalendar(a) },
  trials_at_risk: {
    description: "Trials at Risk from ClinicalTrials.gov, highest risk_score first. Flags (severity): stopped (3: SUSPENDED/TERMINATED/WITHDRAWN updated within lookback_days, why_stopped in detail), overdue (2: active trial whose ESTIMATED primary completion date passed), stale_overdue (+1: and the record was not updated for a year). History-based flags (delayed, enrollment_shortfall, enrollment_cut) need local snapshots and are only in the open-source package. Records carry readout_calendar fields plus risk_flags and risk_score. Not investment advice.",
    inputSchema: { type: "object", properties: {
      sponsor: { type: "string", description: "Lead sponsor name or ticker (alias-resolved)." },
      condition: { type: "string", description: "Condition or disease, free text." },
      intervention: { type: "string", description: "Drug or intervention, free text." },
      phases: { type: "array", items: { type: "string", enum: ["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA", "any"] }, description: "Phases to keep (default PHASE2, PHASE3); [\"any\"] for all." },
      industry_only: { type: "boolean", default: true, description: "Only industry lead sponsors (default true)." },
      lookback_days: { type: "integer", default: 180, maximum: 1095, description: "Days back for newly stopped trials and passed primary completion dates." },
      flags: { type: "array", items: { type: "string", enum: ["stopped", "overdue", "stale_overdue"] }, description: "Keep only trials with any of these flags." },
      max_results: { type: "integer", default: 50, maximum: 300, description: "Maximum trials to return (1-300)." } } },
    async run(a) {
      const lb = Math.max(1, Math.min(+a.lookback_days || 180, 1095)), n = clamp(a.max_results, 300, 50), yr = isoDay(-365);
      const [stopped, overdue] = await Promise.all([ctReadouts(a, "SUSPENDED,TERMINATED,WITHDRAWN", "LastUpdatePostDate", isoDay(-lb), isoDay(0), n),
        ctReadouts(a, ACTIVE, "PrimaryCompletionDate", isoDay(-lb), isoDay(-1), n)]);
      const out = new Map();
      for (const r of stopped) out.set(r.nct_id, { ...r, risk_flags: [{ flag: "stopped", severity: 3, detail: r.status + (r.why_stopped ? `: ${r.why_stopped}` : "") }] });
      for (const r of overdue) { if (r.readout_date_type === "ACTUAL") continue;
        const f = [{ flag: "overdue", severity: 2, detail: `estimated primary completion ${r.readout_date} passed; status ${r.status}` }];
        if (r.last_update_posted && r.last_update_posted < yr) f.push({ flag: "stale_overdue", severity: 1, detail: `record not updated since ${r.last_update_posted}` });
        out.set(r.nct_id, { ...r, risk_flags: f }); }
      let rows = [...out.values()].map(r => ({ ...r, kind: "trial_at_risk", risk_score: r.risk_flags.reduce((x, f) => x + f.severity, 0) }));
      if (Array.isArray(a.flags) && a.flags.length) rows = rows.filter(r => r.risk_flags.some(f => a.flags.includes(f.flag)));
      rows.sort((x, y) => y.risk_score - x.risk_score || (x.readout_date || "").localeCompare(y.readout_date || ""));
      return { trials: rows.slice(0, n), disclaimer: "Registry signals only, not a prediction of trial failure. Not investment advice." };
    } },
  fda_adcom_meetings: {
    description: "FDA advisory committee meeting notices from the Federal Register, newest first: title, publication date, document number and link. Source: Federal Register (U.S. government, public domain).",
    inputSchema: { type: "object", properties: { since: { type: "string", description: "Notice publication date from (YYYY-MM-DD)." }, max_results: { type: "integer", default: 20, maximum: 100, description: "Maximum notices to return (1-100)." } } },
    async run(a) {
      const q = new URLSearchParams({ "conditions[agencies][]": "food-and-drug-administration", "conditions[type][]": "NOTICE",
        "conditions[term]": "\"advisory committee\" \"notice of meeting\"", per_page: "100", order: "newest" });
      if (a.since && /^\d{4}-\d{2}-\d{2}$/.test(a.since)) q.set("conditions[publication_date][gte]", a.since);
      const d = await getJSON(`https://www.federalregister.gov/api/v1/documents.json?${q}`);
      return (d?.results || []).filter(r => /advisory committee/i.test(r.title) && /notice of (public )?meeting/i.test(r.title)).slice(0, clamp(a.max_results, 100, 20)).map(r => ({ title: r.title, publication_date: r.publication_date, document_number: r.document_number, url: r.html_url }));
    } },
};

const json = (body, status = 200, extra = {}) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "access-control-allow-origin": "*", "access-control-expose-headers": "retry-after, x-ratelimit-limit, x-ratelimit-remaining, x-daily-limit, x-daily-remaining, x-daily-reset, x-bcf-tier", "x-content-type-options": "nosniff", "cache-control": "no-store", ...extra } });
const rpcErr = (id, code, message) => ({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });

async function handleRpc(msg) {
  const { id, method, params = {} } = msg || {};
  if (id === undefined) return null; // notification
  switch (method) {
    case "initialize":
      return { jsonrpc: "2.0", id, result: { protocolVersion: PROTOCOL, capabilities: { tools: { listChanged: false } },
        serverInfo: { name: "biocatalystfeed-hosted", version: "0.4.0" },
        instructions: "Read-only public biotech data. Not investment, legal or medical advice. Every record carries verified_as_of, verify_hash, source_url and ticker_confidence. Sources: ClinicalTrials.gov, openFDA (incl. FDA complete response letters; public domain), PubMed, Europe PMC, Federal Register." } };
    case "ping": return { jsonrpc: "2.0", id, result: {} };
    case "tools/list":
      return { jsonrpc: "2.0", id, result: { tools: Object.entries(TOOLS).map(([name, t]) => ({ name, description: t.description, inputSchema: t.inputSchema, annotations: { readOnlyHint: true, openWorldHint: true } })) } };
    case "tools/call": {
      const t = TOOLS[params.name];
      if (!t) return rpcErr(id, -32602, `unknown tool: ${params.name}`);
      try {
        const out = await enrich(await t.run(params.arguments || {})); // provenance + ticker confidence on every record
        return { jsonrpc: "2.0", id, result: { content: [{ type: "text", text: JSON.stringify(out) }], structuredContent: { result: out } } };
      } catch (e) {
        return { jsonrpc: "2.0", id, result: { isError: true, content: [{ type: "text", text: String(e.message || e) }] } };
      }
    }
    default: return rpcErr(id, -32601, `method not found: ${method}`);
  }
}

// Public readout calendar feed for the static site page (biocatalystfeed.github.io/calendar/). Fixed query (90 days,
// PHASE2/3, industry), cached 6 h at the edge so CT.gov sees at most a few requests a day per colo.
async function calendarJson(url) {
  const key = new Request(`${url.origin}/calendar.json`), cache = caches.default;
  const hit = await cache.match(key);
  if (hit) return hit;
  const c = await readoutCalendar({ upcoming_days: 90, max_results: 1000, _sec: false }); // alias-table tickers only (free-plan CPU budget)
  const slim = ["nct_id", "title", "readout_date", "readout_date_type", "phase", "status", "sponsor", "ticker", "ticker_confidence", "conditions", "enrollment", "url", "source_url", "verified_as_of", "verify_hash"];
  const body = { generated_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"), window: c.window, query: { upcoming_days: 90, phases: ["PHASE2", "PHASE3"], industry_only: true },
    count: c.readouts.length, events: c.readouts.map(r => Object.fromEntries(slim.map(k => [k, r[k] ?? null]))), source: "ClinicalTrials.gov API v2",
    note: "Readout = primary completion date (sponsor-reported; ESTIMATED dates often slip). Not investment advice." };
  const res = new Response(JSON.stringify(body), { headers: { "content-type": "application/json", "access-control-allow-origin": "*", "cache-control": "public, max-age=21600" } });
  await cache.put(key, res.clone());
  return res;
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-methods": "POST, GET, DELETE, OPTIONS", "access-control-allow-headers": "content-type, accept, mcp-session-id, mcp-protocol-version, authorization, x-api-key", "access-control-expose-headers": "retry-after, x-ratelimit-limit, x-ratelimit-remaining, x-daily-limit, x-daily-remaining, x-daily-reset, x-bcf-tier" } });
    if (url.pathname === "/" || url.pathname === "/health") return json({ ok: true, service: "BioCatalystFeed hosted MCP", endpoint: "/mcp", terms: "https://github.com/biocatalystfeed/biocatalystfeed/blob/main/TERMS.md", privacy: "https://github.com/biocatalystfeed/biocatalystfeed/blob/main/PRIVACY.md" });
    if (url.pathname === "/calendar.json" && req.method === "GET") return calendarJson(url);
    if (url.pathname !== "/mcp") return json({ error: "not found" }, 404);

    if (req.method === "GET") return json(rpcErr(null, -32000, "SSE stream not supported; use POST"), 405, { allow: "POST" });
    if (req.method === "DELETE") return new Response(null, { status: 204 });
    if (req.method !== "POST") return json(rpcErr(null, -32000, "method not allowed"), 405);

    const client = await resolveClient(req, env);
    if (client.error) return json(rpcErr(null, -32001, client.error), 401);
    let body = null;
    if (!env.UPSTREAM_MCP_URL) { try { body = await req.clone().json(); } catch { return json(rpcErr(null, -32700, "parse error"), 400); } }
    let rl = {};
    if (env.LIMITER) {
      const r = await env.LIMITER.get(env.LIMITER.idFromName(client.id)).hit(body ? toolUnits(body) : 1, client.daily);
      rl = { "x-ratelimit-limit": String(RATE_LIMIT), "x-ratelimit-remaining": String(r.remaining),
        "x-daily-limit": String(r.dailyLimit), "x-daily-remaining": String(r.dailyRemaining), "x-daily-reset": new Date(r.resetAt).toISOString(), "x-bcf-tier": client.tier };
      if (r.reason === "minute") return json(rpcErr(null, -32000, `rate limit exceeded (${RATE_LIMIT} requests/minute); retry in ${Math.max(1, r.retryAfter)} s`), 429, { ...rl, "x-ratelimit-remaining": "0", "retry-after": String(Math.max(1, r.retryAfter)) });
      if (r.reason === "daily") return json(rpcErr(null, -32002, `daily limit reached: ${r.dailyLimit} tool calls per day on the ${client.tier} tier (used ${r.dailyUsed}). Resets at ${new Date(r.resetAt).toISOString()} (00:00 UTC). ${UPGRADE}`), 429, { ...rl, "retry-after": String(Math.max(1, r.dailyReset)) });
    }
    if (env.UPSTREAM_MCP_URL) { // thin-proxy mode to a full Python BCF server
      const h = new Headers(req.headers); h.delete("cookie");
      return fetch(env.UPSTREAM_MCP_URL, { method: "POST", headers: h, body: req.body });
    }
    if (Array.isArray(body)) {
      const out = (await Promise.all(body.slice(0, 10).map(handleRpc))).filter(Boolean);
      return out.length ? json(out, 200, rl) : new Response(null, { status: 202 });
    }
    const out = await handleRpc(body);
    return out ? json(out, 200, rl) : new Response(null, { status: 202 });
  },
};
