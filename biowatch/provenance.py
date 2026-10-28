"""Per-record provenance: verified_as_of, verify_hash, source_url, and ticker-confidence for company -> ticker matching.

verify_hash = "sha256:" + hex SHA-256 of the record's canonical JSON (sorted keys, compact separators, UTF-8) with the
provenance fields themselves (verified_as_of, verify_hash, source_url, retrieved) removed. Re-fetch the record from
source_url, normalize it the same way, and re-hash: an equal hash means the content is unchanged since verified_as_of.
`biowatch.provenance.check(record)` recomputes it.

ticker_confidence (0..1) says how sure the company -> ticker match is:
  1.0  ticker given by the source itself (e.g. SEC filing header)
  0.95 exact match in the curated alias table (fdawatch.aliases)
  0.9  exact normalized name match in SEC company_tickers.json (only if that list was loaded)
  0.6  first-word + suffix-stripped prefix match in SEC company_tickers.json (review before relying on it)
  0.0  no match (ticker null). Private companies, universities and NIH have no ticker by design."""
from __future__ import annotations
import hashlib, json, re
from datetime import datetime, timezone

PROV_FIELDS = ("verified_as_of", "verify_hash", "source_url", "retrieved")
_SEC_NAMES: dict[str, tuple[str, str]] | None = None


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def verify_hash(rec: dict) -> str:
    body = {k: v for k, v in rec.items() if k not in PROV_FIELDS and not k.startswith("ticker_")}
    if isinstance(body.get("provenance"), dict):
        body["provenance"] = {k: v for k, v in body["provenance"].items() if k not in PROV_FIELDS}
    s = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


def stamp(rec: dict, source_url: str | None = None, as_of: str | None = None) -> dict:
    """Add verified_as_of / source_url / verify_hash in place (and return rec). source_url defaults to rec['url']."""
    rec["verified_as_of"] = as_of or now_utc()
    rec["source_url"] = source_url or rec.get("source_url") or rec.get("url")
    rec["verify_hash"] = verify_hash(rec)
    return rec


def stamp_all(rows, source_url=None, as_of=None):
    as_of = as_of or now_utc()
    for r in rows or []:
        if isinstance(r, dict):
            su = source_url(r) if callable(source_url) else source_url
            stamp(r, su, as_of)
    return rows


def check(rec: dict) -> bool:
    return rec.get("verify_hash") == verify_hash(rec)


def _norm(s: str) -> str:
    from fdawatch.aliases import _key
    s = re.sub(r"\b(pharmaceuticals?|therapeutics|biosciences?|biotherapeutics|biopharma(ceuticals)?|holdings|group|"
               r"international|incorporated|limited|gmbh|s a|n v|k k)\b", " ", _key(s or ""))
    return " ".join(s.split())


def load_sec_tickers(sec=None, data: dict | None = None) -> None:
    """Load SEC company_tickers.json once (pass `data` in tests). Without it only the alias table is used."""
    global _SEC_NAMES
    if data is None:
        if sec is None: return
        try: data = sec.get_json("https://www.sec.gov/files/company_tickers.json")
        except Exception: return
    _SEC_NAMES = {}
    for v in data.values():
        _SEC_NAMES.setdefault(_norm(v["title"]), (v["ticker"].upper(), v["title"]))


def ticker_match(name: str | None, source_ticker: str | None = None) -> dict:
    """{ticker, ticker_confidence, ticker_method, ticker_company}."""
    if source_ticker:
        return {"ticker": source_ticker, "ticker_confidence": 1.0, "ticker_method": "source", "ticker_company": name}
    none = {"ticker": None, "ticker_confidence": 0.0, "ticker_method": "none", "ticker_company": None}
    if not name: return none
    from fdawatch.aliases import resolve
    al = resolve(name)
    if al.get("known") and al.get("ticker"):
        return {"ticker": al["ticker"], "ticker_confidence": 0.95, "ticker_method": "alias_table", "ticker_company": al["canonical"]}
    if _SEC_NAMES:
        n = _norm(name)
        if re.search(r"\b(kgaa|darmstadt)\b", n): return none  # Merck KGaA is not Merck & Co. (MRK)
        if n in _SEC_NAMES:
            t, title = _SEC_NAMES[n]
            return {"ticker": t, "ticker_confidence": 0.9, "ticker_method": "sec_exact_name", "ticker_company": title}
        if len(n) >= 4:
            for k, (t, title) in _SEC_NAMES.items():
                if k and k.split()[0] == n.split()[0] and (k.startswith(n) or n.startswith(k)) and len(k.split()[0]) >= 4:
                    return {"ticker": t, "ticker_confidence": 0.6, "ticker_method": "sec_prefix_name", "ticker_company": title}
    return none


def enrich(obj, as_of: str | None = None, source_url=None):
    """Stamp every record dict in a tool result (a dict, a list of dicts, or a dict whose values are such lists) that
    does not already carry verify_hash, and add ticker fields where a company/sponsor name is present."""
    as_of = as_of or now_utc()

    def one(r):
        if not isinstance(r, dict) or "verify_hash" in r: return
        if not any(k in r for k in ("url", "key", "nct_id", "id", "source_url")): return
        if "ticker_confidence" not in r:
            nm = r.get("lead_sponsor") or r.get("sponsor") or r.get("company") or r.get("sponsor_name") or r.get("holder")
            if isinstance(nm, str) and nm:
                tm = ticker_match(nm, r.get("ticker"))
                r.update({k: v for k, v in tm.items() if k != "ticker" or not r.get("ticker")})
        stamp(r, source_url or r.get("source_url") or r.get("url"), as_of)

    if isinstance(obj, list):
        for r in obj: one(r)
    elif isinstance(obj, dict):
        lists = [v for v in obj.values() if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]
        for v in lists:
            for r in v: one(r)
        if not lists: one(obj)
    return obj
