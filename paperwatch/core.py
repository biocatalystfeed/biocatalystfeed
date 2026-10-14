"""PubMed E-utilities + Europe PMC REST + bioRxiv/medRxiv API. Metadata and links only (no abstracts/full text stored).

E-utilities (https://www.ncbi.nlm.nih.gov/books/NBK25497/): no key -> max 3 requests/second (we use 0.4 s spacing).
`tool` is sent always; `email` only if NCBI_EMAIL is set (both are optional, no registration required).
bioRxiv API (https://api.biorxiv.org): no key, no published rate limit -> 1 req/s. It has NO keyword/affiliation search:
we page a date window (30 records/page) and filter locally on title/abstract and corresponding-author institution."""
from __future__ import annotations
import os, re
from datetime import date, timedelta
from functools import lru_cache
from biowatch.http import Throttled
from biowatch.store import ItemStore

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL = "biocatalystfeed"
TRACKED = ("title", "journal", "version", "published_doi")


class PubMedClient(Throttled):
    def __init__(self, **kw):
        mi = kw.pop("min_interval", None)
        super().__init__(min_interval=0.4 if mi is None else mi, **kw)  # <=3 req/s without API key
        self.base = {"tool": TOOL, "retmode": "json"}
        if os.environ.get("NCBI_EMAIL"): self.base["email"] = os.environ["NCBI_EMAIL"]
        if os.environ.get("NCBI_API_KEY"):
            self.base["api_key"] = os.environ["NCBI_API_KEY"]
            if mi is None: self.min_interval = 0.12  # NCBI allows 10 req/s with a key

    def esearch(self, term: str, mindate: str | None = None, maxdate: str | None = None, retmax: int = 100) -> tuple[int, list[str]]:
        p = {**self.base, "db": "pubmed", "term": term, "retmax": retmax, "sort": "pub_date"}
        if mindate or maxdate:
            p.update(datetype="edat", mindate=(mindate or "1900/01/01").replace("-", "/"), maxdate=(maxdate or "3000/12/31").replace("-", "/"))
        d = self.get_json(f"{EUTILS}/esearch.fcgi", params=p)["esearchresult"]
        return int(d.get("count", 0)), d.get("idlist", [])

    def esummary(self, ids: list[str]) -> list[dict]:
        out = []
        for i in range(0, len(ids), 200):
            d = self.get_json(f"{EUTILS}/esummary.fcgi", params={**self.base, "db": "pubmed", "id": ",".join(ids[i:i + 200])})["result"]
            out += [d[u] for u in d.get("uids", [])]
        return out


def pubmed_term(affiliation: list[str] | str | None = None, drug: list[str] | str | None = None, keyword: str | None = None) -> str:
    L = lambda x: [x] if isinstance(x, str) else list(x or [])
    parts = []
    if affiliation: parts.append("(" + " OR ".join(f'"{a}"[ad]' for a in L(affiliation)) + ")")
    if drug: parts.append("(" + " OR ".join(f'"{d}"[tiab] OR "{d}"[nm]' for d in L(drug)) + ")")
    if keyword: parts.append(f"({keyword})")
    if not parts: raise ValueError("give affiliation, drug or keyword")
    return " AND ".join(parts)


def norm_pubmed(s: dict) -> dict:
    ids = {a.get("idtype"): a.get("value") for a in s.get("articleids", [])}
    au = [a.get("name") for a in s.get("authors", []) if a.get("authtype") == "Author"]
    return {"key": f"pmid:{s['uid']}", "source": "pubmed", "id": s["uid"], "title": s.get("title"),
            "authors": ", ".join(au[:6]) + (" et al." if len(au) > 6 else ""), "journal": s.get("fulljournalname") or s.get("source"),
            "date": s.get("sortpubdate", "")[:10].replace("/", "-") or s.get("pubdate"), "doi": ids.get("doi"),
            "pub_types": ", ".join(s.get("pubtype", [])), "version": None, "published_doi": None,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{s['uid']}/"}


def search_pubmed(client: PubMedClient, affiliation=None, drug=None, keyword=None, since=None, until=None, max_records=100) -> dict:
    term = pubmed_term(affiliation, drug, keyword)
    n, ids = client.esearch(term, since, until, retmax=max_records)
    return {"term": term, "total": n, "papers": [norm_pubmed(s) for s in client.esummary(ids)] if ids else []}


EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
RXIV_PUBLISHERS = {"biorxiv": "bioRxiv", "medrxiv": "medRxiv"}


class EuropePMCClient(Throttled):
    """Europe PMC REST API (https://europepmc.org/RestfulWebService): public, no key. Keyword, affiliation (AFF:) and
    date search over MEDLINE/PMC *and* preprints (SRC:PPR incl. bioRxiv/medRxiv). We use 0.5 s spacing and cursor paging."""
    def __init__(self, **kw):
        super().__init__(min_interval=kw.pop("min_interval", 0.5), **kw)

    def search(self, query: str, max_records: int = 100) -> tuple[int, list[dict]]:
        out, cursor, total = [], "*", 0
        while len(out) < max_records:
            d = self.get_json(EPMC, params={"query": query, "format": "json", "resultType": "core", "cursorMark": cursor,
                                            "pageSize": min(1000, max_records - len(out)), "sort": "P_PDATE_D desc"})
            total = int(d.get("hitCount") or 0)
            res = (d.get("resultList") or {}).get("result") or []
            out += res
            nxt = d.get("nextCursorMark")
            if not res or not nxt or nxt == cursor: break
            cursor = nxt
        return total, out[:max_records]


def _q(t: str) -> str:
    return '"' + t.replace('"', "") + '"'


def epmc_query(affiliation=None, drug=None, keyword=None, since=None, until=None, preprints: str | None = None) -> str:
    """preprints: None = everything; 'only' = SRC:PPR; 'rxiv' = bioRxiv/medRxiv preprints only."""
    L = lambda x: [x] if isinstance(x, str) else list(x or [])
    parts = []
    if affiliation: parts.append("(" + " OR ".join(f"AFF:{_q(a)}" for a in L(affiliation)) + ")")
    if drug: parts.append("(" + " OR ".join(f"(TITLE:{_q(d)} OR ABSTRACT:{_q(d)} OR CHEM:{_q(d)})" for d in L(drug)) + ")")
    if keyword: parts.append(f"({keyword})")
    if not parts: raise ValueError("give affiliation, drug or keyword")
    if since or until: parts.append(f"FIRST_PDATE:[{since or '1900-01-01'} TO {until or '3000-12-31'}]")
    if preprints == "only": parts.append("SRC:PPR")
    elif preprints == "rxiv": parts.append('SRC:PPR AND (PUBLISHER:"bioRxiv" OR PUBLISHER:"medRxiv")')
    return " AND ".join(parts)


def norm_epmc(r: dict) -> dict:
    ppr = r.get("source") == "PPR"
    pub = ((r.get("bookOrReportDetails") or {}).get("publisher") or "")
    srv = pub.lower() if pub.lower() in RXIV_PUBLISHERS else None
    ji = r.get("journalInfo") or {}
    au = (r.get("authorString") or "").rstrip(".").split(", ")
    doi = r.get("doi")
    if ppr and srv and doi: url = f"https://doi.org/{doi}"
    elif r.get("pmid"): url = f"https://europepmc.org/article/MED/{r['pmid']}"
    else: url = f"https://europepmc.org/article/{r.get('source')}/{r.get('id')}"
    return {"key": f"doi:{doi.lower()}" if doi else f"epmc:{r.get('source')}:{r.get('id')}", "source": "europepmc",
            "origin": srv or ("preprint" if ppr else "journal"), "id": r.get("id"), "pmid": r.get("pmid"),
            "title": (r.get("title") or "").rstrip("."), "authors": ", ".join(au[:6]) + (" et al." if len(au) > 6 else ""),
            "journal": ((ji.get("journal") or {}).get("title")) or pub or None, "date": r.get("firstPublicationDate"),
            "doi": doi, "version": str(r["versionNumber"]) if r.get("versionNumber") else None, "published_doi": None,
            "is_preprint": ppr, "url": url,
            "keywords": list(((r.get("keywordList") or {}).get("keyword")) or [])}


def search_europepmc(client: EuropePMCClient, affiliation=None, drug=None, keyword=None, since=None, until=None,
                     max_records: int = 100, preprints: str | None = None) -> dict:
    q = epmc_query(affiliation, drug, keyword, since, until, preprints)
    n, res = client.search(q, max_records=max_records)
    return {"query": q, "total": n, "papers": [norm_epmc(r) for r in res]}


def search_preprints_fast(epmc: EuropePMCClient | None, rx: "RxivClient | None", affiliation=None, drug=None, keyword=None,
                          days: int = 14, since=None, until=None, max_records: int = 200) -> list[dict]:
    """bioRxiv/medRxiv preprints via Europe PMC keyword search (fast: 1-2 calls). Falls back to paging the bioRxiv API
    if Europe PMC errors. Note Europe PMC matches affiliation for any author, the bioRxiv fallback only the corresponding one."""
    until = until or date.today().isoformat()
    since = since or (date.fromisoformat(until) - timedelta(days=days)).isoformat()
    if epmc is not None:
        try:
            rows = search_europepmc(epmc, affiliation, drug, keyword, since, until, max_records, preprints="rxiv")["papers"]
            for r in rows: r["source"] = r["origin"] if r["origin"] in RXIV_PUBLISHERS else "europepmc"; r["via"] = "europepmc"
            return rows
        except Exception:
            if rx is None: raise
    return search_preprints(rx, affiliation, drug, keyword, since=since, until=until) if rx is not None else []


class RxivClient(Throttled):
    def __init__(self, **kw):
        super().__init__(min_interval=kw.pop("min_interval", 1.0), **kw)
        self._cache: dict = {}

    def window(self, server: str, since: str, until: str, max_pages: int = 200) -> list[dict]:
        """All preprint records posted in [since, until] (cached per run)."""
        k = (server, since, until)
        if k in self._cache: return self._cache[k]
        out, cursor = [], 0
        for _ in range(max_pages):
            d = self.get_json(f"https://api.biorxiv.org/details/{server}/{since}/{until}/{cursor}/json")
            col = d.get("collection") or []
            out += col
            msg = (d.get("messages") or [{}])[0]
            cursor += len(col)
            if not col or cursor >= int(msg.get("total", 0) or 0): break
        self._cache[k] = out
        return out


def _match(text: str, terms: list[str]) -> bool:
    t = (text or "").lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(x.lower()) + r"(?![a-z0-9])", t) for x in terms)


def norm_rxiv(r: dict) -> dict:
    srv = (r.get("server") or "biorxiv").lower()
    return {"key": f"doi:{r['doi']}", "source": srv, "id": r["doi"], "title": r.get("title"),
            "authors": ", ".join((r.get("authors") or "").split("; ")[:6]) + (" et al." if (r.get("authors") or "").count(";") >= 6 else ""),
            "journal": srv, "date": r.get("date"), "doi": r["doi"], "version": r.get("version"),
            "corresponding_institution": r.get("author_corresponding_institution"), "license": r.get("license"),
            "category": r.get("category"), "published_doi": None if r.get("published") in (None, "NA") else r.get("published"),
            "url": f"https://www.{srv}.org/content/{r['doi']}v{r.get('version') or 1}"}


def search_preprints(client: RxivClient, affiliation=None, drug=None, keyword=None, days: int = 14,
                     since: str | None = None, until: str | None = None, servers=("biorxiv", "medrxiv")) -> list[dict]:
    """affiliation matches the corresponding author's institution only (the API exposes nothing else);
    drug/keyword match title+abstract. Terms are OR'd within a field, AND'd across fields."""
    L = lambda x: [x] if isinstance(x, str) else list(x or [])
    until = until or date.today().isoformat()
    since = since or (date.fromisoformat(until) - timedelta(days=days)).isoformat()
    out = {}
    for srv in servers:
        for r in client.window(srv, since, until):
            if affiliation and not _match(r.get("author_corresponding_institution"), L(affiliation)): continue
            txt = (r.get("title") or "") + " " + (r.get("abstract") or "")
            if drug and not _match(txt, L(drug)): continue
            if keyword and not _match(txt, L(keyword)): continue
            n = norm_rxiv({**r, "server": r.get("server") or srv})
            if n["key"] not in out or (n["version"] or "") > (out[n["key"]]["version"] or ""): out[n["key"]] = n
    return sorted(out.values(), key=lambda x: x["date"] or "", reverse=True)


def combined(rows: list[dict], query=(), exclude=None, rank: bool = False) -> list[dict]:
    """Cross-source dedup (DOI/PMID) + optional exclusion terms + optional relevance ranking (else newest first)."""
    from biowatch import filters
    rows = filters.exclude(filters.dedup(rows), exclude)
    return filters.rank(rows, *query) if rank else sorted(rows, key=lambda x: x.get("date") or "", reverse=True)


def search_all(pm: PubMedClient | None, epmc: EuropePMCClient | None, rx: RxivClient | None, affiliation=None, drug=None,
               keyword=None, since=None, until=None, preprint_days: int = 14, max_records: int = 100, exclude=None,
               rank: bool = False) -> dict:
    """PubMed + Europe PMC + bioRxiv/medRxiv preprints (Europe PMC first, bioRxiv API fallback), merged and deduped.
    Pass None for any client to skip that source. Preprints use Europe PMC when `epmc` is given, else the bioRxiv API."""
    out = {"pubmed": None, "europepmc": None, "preprints": [], "errors": {}}
    rows = []
    if pm is not None:
        try:
            out["pubmed"] = r = search_pubmed(pm, affiliation, drug, keyword, since=since, until=until, max_records=max_records)
            rows += r["papers"]; out["pubmed"] = {"term": r["term"], "total": r["total"]}
        except Exception as e: out["errors"]["pubmed"] = f"{type(e).__name__}: {e}"
    if epmc is not None:
        try:
            r = search_europepmc(epmc, affiliation, drug, keyword, since=since, until=until, max_records=max_records)
            rows += r["papers"]; out["europepmc"] = {"query": r["query"], "total": r["total"]}
        except Exception as e: out["errors"]["europepmc"] = f"{type(e).__name__}: {e}"
    if (epmc is not None or rx is not None) and preprint_days > 0:
        try:
            pre = search_preprints_fast(epmc, rx, affiliation, drug, keyword, days=preprint_days, max_records=max_records)
            out["preprints"] = [p["key"] for p in pre]; rows += pre
        except Exception as e: out["errors"]["preprints"] = f"{type(e).__name__}: {e}"
    out["papers"] = combined(rows, (affiliation, drug, keyword), exclude, rank)
    return out


def company_papers(pm: PubMedClient, rx: RxivClient | None, alias: dict, since: str, preprint_days: int = 14,
                   max_records: int = 50, epmc: EuropePMCClient | None = None) -> dict:
    aff = alias.get("pubmed_affil") or []
    drugs = alias.get("drugs") or []
    res = {"pubmed_affiliation": search_pubmed(pm, affiliation=aff, since=since, max_records=max_records) if aff else None,
           "pubmed_drugs": search_pubmed(pm, drug=drugs, since=since, max_records=max_records) if drugs else None,
           "preprints": [], "preprint_window_days": preprint_days}
    if (rx is not None or epmc is not None) and (aff or drugs):
        rxa = alias.get("preprint_affil") or aff
        seen = {}
        for p in (search_preprints_fast(epmc, rx, affiliation=rxa, days=preprint_days) if rxa else []) + \
                 (search_preprints_fast(epmc, rx, drug=drugs, days=preprint_days) if drugs else []):
            seen[p["key"]] = p
        res["preprints"] = sorted(seen.values(), key=lambda x: x["date"] or "", reverse=True)
    return res


def store(path: str) -> ItemStore:
    return ItemStore(path, "paper", TRACKED, new_kind="new_paper")


def run_watch(pm: PubMedClient | None, rx: RxivClient | None, st: ItemStore, watch: str, affiliation=None, drug=None, keyword=None,
              since=None, preprint_days: int = 14, max_records: int = 200, epmc: EuropePMCClient | None = None,
              exclude=None, epmc_journals: bool = True, preprints_via_epmc: bool = True) -> dict:
    """Sources: PubMed (pm), Europe PMC (epmc; journals unless epmc_journals=False), preprints (Europe PMC unless
    preprints_via_epmc=False, with the bioRxiv API `rx` as fallback/primary). preprint_days=0 skips preprints."""
    rows = search_pubmed(pm, affiliation, drug, keyword, since=since, max_records=max_records)["papers"] if pm is not None else []
    if epmc is not None and epmc_journals:
        rows += search_europepmc(epmc, affiliation, drug, keyword, since=since, max_records=max_records)["papers"]
    pe = epmc if preprints_via_epmc else None
    if preprint_days > 0 and (rx is not None or pe is not None):
        rows += search_preprints_fast(pe, rx, affiliation, drug, keyword, days=preprint_days)
    rows = combined(rows, exclude=exclude)
    q = {"affiliation": affiliation, "drug": drug, "keyword": keyword, "since": since, "exclude": exclude}
    info = st.ingest(watch, rows, query=q)
    info["changes_detail"] = st.changes(watch=watch, run_id=info["run_id"])
    return info
