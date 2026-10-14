from biowatch import filters
from paperwatch import core as pw


def test_exclude_terms_normalize():
    assert filters.exclude_terms('mice, "rat" ,-canine') == ["mice", "rat", "canine"]
    assert filters.exclude_terms(None) == []


def test_exclude_wildcard_and_comma_string():
    rows = [{"title": "Murine model of NASH"}, {"title": "Rat toxicology"}, {"title": "Phase 3 in adults"}]
    assert [r["title"] for r in filters.exclude(rows, "murin*, rat")] == ["Phase 3 in adults"]


def test_rank_full_coverage_and_plurals():
    rows = [{"title": "Resmetirom liver study", "date": "2026-01-01"},
            {"title": "Resmetirom update", "date": "2026-09-01"},
            {"title": "Unrelated", "date": "2026-10-01"}]
    out = filters.rank(rows, "resmetirom", "studies")
    assert out[0]["title"] == "Resmetirom liver study" and out[-1]["relevance"] == 0


def test_rank_phrase_bonus():
    rows = [{"title": "Fatty disease of the liver"}, {"title": "Fatty liver disease outcomes"}]
    out = filters.rank(rows, '"fatty liver"')
    assert out[0]["title"] == "Fatty liver disease outcomes"


def test_norm_epmc_keywords():
    r = pw.norm_epmc({"source": "MED", "id": "1", "pmid": "1", "title": "X.", "keywordList": {"keyword": ["NASH"]}})
    assert r["keywords"] == ["NASH"] and r["url"].endswith("/MED/1")
    assert filters.exclude([r], ["nash"]) == []
