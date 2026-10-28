"""Static readout calendar page (HTML + JSON) for the public site. Data are embedded so the page works with no
backend; on load it also tries the hosted worker's /calendar.json (same CT.gov query, cached) and re-renders if newer."""
from __future__ import annotations
import html as _h, json

LIVE = "https://bcf-mcp.lively-recipe-5a12.workers.dev/calendar.json"
SLIM = ("nct_id", "title", "readout_date", "readout_date_type", "phase", "status", "sponsor", "ticker", "ticker_confidence",
        "conditions", "enrollment", "url", "source_url", "verified_as_of", "verify_hash")


def slim(events: list[dict]) -> list[dict]:
    return [{k: e.get(k) for k in SLIM} for e in events]


def payload(events, generated_at, window, query) -> dict:
    return {"generated_at": generated_at, "window": window, "query": query, "count": len(events), "events": slim(events),
            "source": "ClinicalTrials.gov API v2", "note": "Readout = primary completion date (sponsor-reported; ESTIMATED dates often slip). Not investment advice."}


def render(data: dict, live_url: str = LIVE) -> str:
    rows = "".join(
        f"<tr><td>{_h.escape(e['readout_date'] or '')}{'' if e['readout_date_type'] == 'ACTUAL' else ' <small>est.</small>'}</td>"
        f"<td>{_h.escape((e['phase'] or '').replace('PHASE', 'P'))}</td><td>{_h.escape(e['sponsor'] or '')}"
        + (f" <b>{_h.escape(e['ticker'])}</b>" if e.get("ticker") else "") + "</td>"
        f"<td><a href=\"{_h.escape(e['url'] or '')}\">{_h.escape(e['nct_id'])}</a> {_h.escape((e['title'] or '')[:140])}</td>"
        f"<td>{_h.escape((e['conditions'] or '')[:80])}</td></tr>" for e in data["events"][:150])
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trial readout calendar - BioCatalystFeed</title>
<meta name="description" content="Upcoming clinical trial readouts (primary completion dates) from ClinicalTrials.gov, filterable by sponsor, ticker, condition and phase. Free, open source.">
<link rel="icon" href="/favicon.svg"><link rel="stylesheet" href="/style.css">
<style>table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border-bottom:1px solid #ddd;padding:6px;text-align:left;vertical-align:top}}
th{{cursor:pointer}}.f{{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}}.f input,.f select{{padding:6px}}small{{color:#777}}</style></head>
<body><main style="max-width:1100px;margin:auto;padding:16px">
<p><a href="/">BioCatalystFeed</a></p>
<h1>Trial readout calendar</h1>
<p>Industry-sponsored Phase 2/3 trials whose <b>primary completion date</b> falls in the window, soonest first. Sponsor-reported in
ClinicalTrials.gov; <small>est.</small> dates often slip, and top-line results usually follow weeks to months later. Tickers are
matched by name with a confidence score. Each row links to the registry record. Not investment advice.</p>
<p id="meta"><small>Window {_h.escape(data['window'][0])} to {_h.escape(data['window'][1])} - {data['count']} trials - generated {_h.escape(data['generated_at'])}
- <a href="calendar.json">JSON</a></small></p>
<div class="f"><input id="q" placeholder="sponsor, ticker, drug, title"><input id="c" placeholder="condition">
<select id="p"><option value="">all phases</option><option>PHASE2</option><option>PHASE3</option></select>
<label><input type="checkbox" id="t"> ticker only</label></div>
<table><thead><tr><th>Readout</th><th>Phase</th><th>Sponsor</th><th>Trial</th><th>Conditions</th></tr></thead><tbody id="b">{rows}</tbody></table>
<p><small>Same data via CLI: <code>bcf readouts search --upcoming 90</code>; MCP tool <code>readout_calendar</code>. Source: ClinicalTrials.gov API v2 (NLM).</small></p>
</main>
<script id="data" type="application/json">{blob}</script>
<script>
let D=JSON.parse(document.getElementById('data').textContent);const $=i=>document.getElementById(i);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
function draw(){{const q=$('q').value.toLowerCase(),c=$('c').value.toLowerCase(),p=$('p').value,t=$('t').checked;
$('b').innerHTML=D.events.filter(e=>(!q||[e.sponsor,e.ticker,e.title,e.nct_id].join(' ').toLowerCase().includes(q))&&(!c||(e.conditions||'').toLowerCase().includes(c))&&(!p||(e.phase||'').includes(p))&&(!t||e.ticker))
.map(e=>`<tr><td>${{esc(e.readout_date)}}${{e.readout_date_type==='ACTUAL'?'':' <small>est.</small>'}}</td><td>${{esc((e.phase||'').replaceAll('PHASE','P'))}}</td><td>${{esc(e.sponsor)}}${{e.ticker?' <b>'+esc(e.ticker)+'</b>':''}}</td><td><a href="${{esc(e.url)}}">${{esc(e.nct_id)}}</a> ${{esc((e.title||'').slice(0,140))}}</td><td>${{esc((e.conditions||'').slice(0,80))}}</td></tr>`).join('');}}
['q','c','p','t'].forEach(i=>$(i).addEventListener('input',draw));
fetch({json.dumps(live_url)}).then(r=>r.ok?r.json():null).then(j=>{{if(j&&j.events&&Date.parse(j.generated_at)-Date.parse(D.generated_at)>864e5){{D=j;$('meta').innerHTML='<small>Window '+esc(j.window[0])+' to '+esc(j.window[1])+' - '+j.count+' trials - live data '+esc(j.generated_at)+'</small>';draw();}}}}).catch(()=>{{}});
</script></body></html>
"""
