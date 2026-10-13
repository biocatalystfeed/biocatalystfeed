"""Cross-tool result helpers: exclusion terms, relevance ranking, cross-source dedup (DOI / PMID)."""
from __future__ import annotations
import re

TEXT_FIELDS = ("title", "brief_title", "official_title", "conditions", "interventions", "brand_names", "generic_names",
               "journal", "org_name", "pis", "corresponding_institution", "lead_sponsor", "company", "keywords")


def _L(x) -> list[str]:
    if not x: return []
    return [x] if isinstance(x, str) else [t for t in x if t]


def _text(r: dict, fields=TEXT_FIELDS) -> str:
    parts = []
    for f in fields:
        v = r.get(f)
        if isinstance(v, (list, tuple)): v = " ".join(map(str, v))
        if v: parts.append(str(v))
    return " ".join(parts).lower()


def _hit(text: str, term: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", text) is not None


def exclude(rows: list[dict], terms, fields=TEXT_FIELDS) -> list[dict]:
    """Drop rows whose text fields contain any exclusion term (whole word/phrase, case-insensitive)."""
    terms = _L(terms)
    if not terms: return rows
    return [r for r in rows if not any(_hit(_text(r, fields), t) for t in terms)]


def query_terms(*values) -> list[str]:
    """Flatten query inputs (strings / lists, PubMed-style syntax) into plain lowercase terms for ranking."""
    out = []
    for v in values:
        for s in _L(v):
            s = re.sub(r"\[[a-zA-Z]+\]|\b(AND|OR|NOT)\b|[()]", " ", str(s))
            out += [q.strip().lower() for q in re.findall(r'"([^"]+)"', s)]
            s = re.sub(r'"[^"]+"', " ", s)
            out += [w.lower() for w in s.split() if len(w) > 2]
    return list(dict.fromkeys(out))


def score(r: dict, terms: list[str]) -> float:
    """Transparent relevance: each term found in the title scores 3, found only in other text fields scores 1."""
    title = (r.get("title") or r.get("brief_title") or "").lower()
    rest = _text(r)
    return float(sum(3 if _hit(title, t) else 1 if _hit(rest, t) else 0 for t in terms))


def rank(rows: list[dict], *query, date_field: str = "date") -> list[dict]:
    """Annotate rows with `relevance` and sort by it (desc), then by date (desc)."""
    terms = query_terms(*query)
    for r in rows: r["relevance"] = score(r, terms)
    return sorted(rows, key=lambda r: (r["relevance"], str(r.get(date_field) or "")), reverse=True)


def norm_doi(d: str | None) -> str | None:
    if not d: return None
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", d.strip().lower())
    return d or None


SOURCE_PRIORITY = {"pubmed": 0, "europepmc": 1, "biorxiv": 2, "medrxiv": 2}


def _ids(r: dict) -> list[str]:
    out = []
    if norm_doi(r.get("doi")): out.append("doi:" + norm_doi(r.get("doi")))
    if norm_doi(r.get("published_doi")): out.append("doi:" + norm_doi(r.get("published_doi")))
    pmid = r.get("pmid") or (r.get("id") if r.get("source") == "pubmed" else None)
    if pmid: out.append(f"pmid:{pmid}")
    return out


def dedup(rows: list[dict]) -> list[dict]:
    """Merge records sharing a DOI (incl. a preprint's published DOI) or PMID across sources (transitively). The record
    from the highest-priority source wins (PubMed > Europe PMC > bioRxiv/medRxiv); `sources` lists every source."""
    parent = list(range(len(rows)))
    def find(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    seen: dict[str, int] = {}
    for i, r in enumerate(rows):
        for k in _ids(r):
            if k in seen: parent[find(i)] = find(seen[k])
            else: seen[k] = i
    groups: dict[int, list[int]] = {}
    for i in range(len(rows)): groups.setdefault(find(i), []).append(i)
    out = []
    for members in sorted(groups.values(), key=min):
        ms = sorted((rows[i] for i in members), key=lambda x: SOURCE_PRIORITY.get(x.get("source"), 9))
        g = dict(ms[0], sources=[])
        for r in ms:
            for s in r.get("sources") or [r.get("source")]:
                if s not in g["sources"]: g["sources"].append(s)
            for f in ("doi", "pmid", "journal"):
                if not g.get(f) and r.get(f): g[f] = r[f]
        out.append(g)
    return out
