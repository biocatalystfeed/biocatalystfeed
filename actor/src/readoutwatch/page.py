"""Static readout calendar page (HTML + JSON) for the public site. Data are embedded so the page works with no
backend; on load it also tries the hosted worker's /calendar.json (same CT.gov query, cached) and re-renders if newer."""
from __future__ import annotations
import html as _h, json, os, re
from urllib.parse import quote as _quote

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
        + (f" <b><a href=\"company/{_q(e['ticker'])}/\">{_h.escape(e['ticker'])}</a></b>" if e.get("ticker") else "") + "</td>"
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
- <a href="calendar.json">JSON</a> - <a href="calendar.ics">subscribe (.ics)</a> - <a href="company/">by company</a>
- <a href="month/">by month</a></small></p>
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
.map(e=>`<tr><td>${{esc(e.readout_date)}}${{e.readout_date_type==='ACTUAL'?'':' <small>est.</small>'}}</td><td>${{esc((e.phase||'').replaceAll('PHASE','P'))}}</td><td>${{esc(e.sponsor)}}${{e.ticker?' <b><a href="company/'+encodeURIComponent(e.ticker)+'/">'+esc(e.ticker)+'</a></b>':''}}</td><td><a href="${{esc(e.url)}}">${{esc(e.nct_id)}}</a> ${{esc((e.title||'').slice(0,140))}}</td><td>${{esc((e.conditions||'').slice(0,80))}}</td></tr>`).join('');}}
['q','c','p','t'].forEach(i=>$(i).addEventListener('input',draw));
fetch({json.dumps(live_url)}).then(r=>r.ok?r.json():null).then(j=>{{if(j&&j.events&&Date.parse(j.generated_at)-Date.parse(D.generated_at)>864e5){{D=j;$('meta').innerHTML='<small>Window '+esc(j.window[0])+' to '+esc(j.window[1])+' - '+j.count+' trials - live data '+esc(j.generated_at)+'</small>';draw();}}}}).catch(()=>{{}});
</script></body></html>
"""


SITE = "https://biocat.ai"
_SAFE = re.compile(r"[^A-Za-z0-9.\-]")


def _q(ticker: str) -> str:
    return _quote(slug(ticker))


def slug(ticker: str) -> str:
    """Path-safe ticker (e.g. 'BRK.B' stays, anything odd becomes '-')."""
    return _SAFE.sub("-", str(ticker or "").strip().upper())[:12] or "-"


_CSS = ("table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #ddd;padding:6px;"
        "text-align:left;vertical-align:top}small{color:#777}")


def _table(events: list[dict], prefix: str) -> str:
    rows = "".join(
        f"<tr><td>{_h.escape(e.get('readout_date') or '')}{'' if e.get('readout_date_type') == 'ACTUAL' else ' <small>est.</small>'}</td>"
        f"<td>{_h.escape((e.get('phase') or '').replace('PHASE', 'P'))}</td><td>{_h.escape(e.get('sponsor') or '')}"
        + (f" <b><a href=\"{prefix}company/{_q(e['ticker'])}/\">{_h.escape(e['ticker'])}</a></b>" if e.get("ticker") else "") + "</td>"
        f"<td><a href=\"{_h.escape(e.get('url') or '')}\">{_h.escape(e.get('nct_id') or '')}</a> {_h.escape((e.get('title') or '')[:160])}</td>"
        f"<td>{_h.escape((e.get('conditions') or '')[:100])}</td><td>{_h.escape(str(e.get('enrollment') or ''))}</td></tr>" for e in events)
    return ("<table><thead><tr><th>Readout</th><th>Phase</th><th>Sponsor</th><th>Trial</th><th>Conditions</th><th>Enrollment</th>"
            f"</tr></thead><tbody>{rows or '<tr><td colspan=6>No trials in this window.</td></tr>'}</tbody></table>")


def _jsonld(events: list[dict], page_url: str) -> str:
    """schema.org Event list (MedicalTrial as about) so search engines can read dates; ESTIMATED is stated in the name."""
    items = [{"@type": "Event", "name": f"{e.get('nct_id')} primary completion"
              + ("" if e.get("readout_date_type") == "ACTUAL" else " (estimated)") + f": {(e.get('title') or '')[:110]}",
              "startDate": e.get("readout_date"), "eventStatus": "https://schema.org/EventScheduled",
              "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
              "location": {"@type": "VirtualLocation", "url": e.get("url")},
              "organizer": {"@type": "Organization", "name": e.get("sponsor")}, "url": e.get("url")}
             for e in events[:100] if e.get("readout_date")]
    blob = json.dumps({"@context": "https://schema.org", "@type": "ItemList", "url": page_url,
                       "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": x} for i, x in enumerate(items)]},
                      separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/ld+json">{blob}</script>'


def _page(title: str, desc: str, path: str, body: str, data: dict, events: list[dict] | None = None, depth: int = 1) -> str:
    up = "../" * depth
    url = SITE + path
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_h.escape(title)} - BioCatalystFeed</title>
<meta name="description" content="{_h.escape(desc)}"><link rel="canonical" href="{_h.escape(url)}">
<link rel="icon" href="/favicon.svg"><link rel="stylesheet" href="/style.css"><style>{_CSS}</style>
{_jsonld(events, url) if events else ''}</head>
<body><main style="max-width:1100px;margin:auto;padding:16px">
<p><a href="/">BioCatalystFeed</a> / <a href="{up}">Trial readout calendar</a> / <a href="{up}company/">Companies</a> / <a href="{up}month/">Months</a></p>
{body}
<p><small>Readout = ClinicalTrials.gov primary completion date (sponsor-reported; <small>est.</small> dates often slip; top-line
results usually follow weeks to months later). Tickers are matched by sponsor name with a confidence score. Generated
{_h.escape(data['generated_at'])} from ClinicalTrials.gov API v2 (NLM). Same data: <code>bcf readouts search</code>, MCP
<code>readout_calendar</code>. Not investment advice.</small></p>
</main></body></html>
"""


def by_ticker(events: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for e in events:
        if e.get("ticker"): out.setdefault(slug(e["ticker"]), []).append(e)
    return out


def by_month(events: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for e in events:
        d = e.get("readout_date") or ""
        if len(d) >= 7: out.setdefault(d[:7], []).append(e)
    return out


def write_site(data: dict, out: str, base_path: str = "/calendar/", live_url: str = LIVE) -> dict:
    """Write the calendar page plus SEO sub-pages and calendar feeds under `out`:
    index.html, calendar.json, calendar.ics; company/index.html and company/TICKER/{index.html,calendar.ics} for every
    matched ticker; month/index.html and month/YYYY-MM/index.html; sitemap.xml (calendar URLs). Returns counts."""
    from biowatch import ics
    ev = data["events"]
    os.makedirs(out, exist_ok=True)

    def w(rel: str, text: str):
        p = os.path.join(out, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", newline="") as f: f.write(text)

    w("calendar.json", json.dumps(data, separators=(",", ":")))
    w("index.html", render(data, live_url))
    w("calendar.ics", ics.calendar("BioCatalystFeed trial readouts (industry Phase 2/3)", ev))
    urls = [base_path, base_path + "company/", base_path + "month/"]
    tick = by_ticker(ev)
    names = {t: (es[0].get("sponsor") or t) for t, es in tick.items()}
    for t, es in tick.items():
        path = f"{base_path}company/{t}/"
        nm = names[t]
        ph3 = sum(1 for e in es if "PHASE3" in (e.get("phase") or ""))
        body = (f"<h1>{_h.escape(t)} upcoming trial readouts</h1><p>{_h.escape(nm)}: {len(es)} industry-sponsored Phase 2/3 "
                f"trial(s) with a primary completion date between {_h.escape(data['window'][0])} and {_h.escape(data['window'][1])}"
                f" ({ph3} Phase 3). <a href=\"calendar.ics\">Subscribe to {_h.escape(t)} readouts (.ics)</a>.</p>"
                + _table(es, "../../"))
        w(f"company/{t}/index.html", _page(f"{t} ({nm}) upcoming clinical trial readouts", f"Upcoming clinical trial readouts "
          f"(primary completion dates) for {nm} ({t}) from ClinicalTrials.gov: {len(es)} trial(s), with phase, status and source links.",
          path, body, data, es, depth=2))
        w(f"company/{t}/calendar.ics", ics.calendar(f"BioCatalystFeed {t} trial readouts", es))
        urls.append(path)
    lis = "".join(f"<li><a href=\"{_q(t)}/\">{_h.escape(t)}</a> {_h.escape(names[t])} - {len(tick[t])} readout(s)</li>"
                  for t in sorted(tick))
    w("company/index.html", _page("Biotech companies with upcoming trial readouts", f"{len(tick)} public companies with "
      "upcoming Phase 2/3 primary completion dates on ClinicalTrials.gov, by ticker.", base_path + "company/",
      f"<h1>Companies with upcoming readouts</h1><p>{len(tick)} tickers matched. Trials whose sponsor has no ticker match are on the "
      f"<a href=\"../\">main calendar</a>.</p><ul>{lis}</ul>", data))
    mon = by_month(ev)
    for m, es in mon.items():
        path = f"{base_path}month/{m}/"
        w(f"month/{m}/index.html", _page(f"Clinical trial readouts in {m}", f"{len(es)} industry Phase 2/3 trials with a "
          f"primary completion date in {m} (ClinicalTrials.gov), with sponsors, tickers and source links.", path,
          f"<h1>Trial readouts in {_h.escape(m)}</h1><p>{len(es)} trial(s).</p>" + _table(es, "../../"), data, es, depth=2))
        urls.append(path)
    w("month/index.html", _page("Clinical trial readouts by month", "Upcoming industry Phase 2/3 trial readouts by month.",
      base_path + "month/", "<h1>Readouts by month</h1><ul>" + "".join(
          f"<li><a href=\"{m}/\">{m}</a> - {len(mon[m])} trial(s)</li>" for m in sorted(mon)) + "</ul>", data))
    day = (data.get("generated_at") or "")[:10]
    w("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
      + "".join(f"<url><loc>{SITE}{_h.escape(u)}</loc>" + (f"<lastmod>{day}</lastmod>" if day else "") + "</url>" for u in urls)
      + "</urlset>\n")
    return {"events": len(ev), "companies": len(tick), "months": len(mon), "urls": len(urls)}
