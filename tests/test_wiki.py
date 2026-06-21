"""Tests for the stdlib WikiIndex (runtime wiki-cache access)."""

from __future__ import annotations

import json
from pathlib import Path

from cricket.lore.wiki import WikiIndex, _capitalized_phrases


def _make_cache(root: Path) -> None:
    pages = root / "pages"
    pages.mkdir(parents=True)
    # A Main-namespace article: no index summary -> lead comes from the page file.
    (pages / "biscuit-baron.txt").write_text(
        "TITLE: Biscuit Baron\nNAMESPACE: 0 (Main)\nLAST_EDIT: 2025-01-01T00:00:00Z\n"
        "======================================================================\n"
        "[[File:bb.png|thumb|right|A logo]]\n"
        "{{Business}}\n\n"
        "'''Biscuit Baron''' is the galaxy's largest fast-casual dining chain, "
        "later bought by the [[Golden Bantha Group]].\n\n"
        "[[Category:Business]]\n",
        encoding="utf-8",
    )
    records = [
        {"title": "RPlog:Ghastly Gala", "ns": 1, "ns_name": "RPlog",
         "path": "pages/ghastly-gala.txt", "last_edit": "", "characters": ["Cricket", "Zubindi Hakoon"],
         "rl_date": "2024-04-01", "aby_year": 33, "factions": [],
         "summary": "Cricket festoons himself with red cups at a grotesque-themed gala."},
        {"title": "RPlog:Charity Ball", "ns": 1, "ns_name": "RPlog",
         "path": "pages/charity-ball.txt", "last_edit": "", "characters": ["Cricket"],
         "rl_date": "2025-03-01", "aby_year": 34, "factions": [],
         "summary": "Cricket schemes at the Arkanis Sector children's fundraiser ball."},
        {"title": "Biscuit Baron", "ns": 0, "ns_name": "Main",
         "path": "pages/biscuit-baron.txt", "last_edit": "", "characters": [],
         "rl_date": "", "aby_year": None, "factions": [], "summary": ""},
        {"title": "Talk:Something", "ns": 1, "ns_name": "Talk",
         "path": "pages/talk.txt", "last_edit": "", "characters": [], "summary": "noise"},
    ]
    with open(root / "index.jsonl", "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def test_capitalized_phrases():
    out = _capitalized_phrases("what about the Golden Bantha Group and Coruscant?")
    assert "Golden Bantha Group" in out
    assert "Coruscant" in out
    # 'and' must split, not join.
    assert "Golden Bantha Group and Coruscant" not in out


def test_load_filters_noise(tmp_path):
    _make_cache(tmp_path)
    wi = WikiIndex(tmp_path)
    assert wi.loaded
    # Talk namespace is filtered out; 3 useful records remain.
    assert len(wi._recs) == 3


def test_lookup_and_search(tmp_path):
    _make_cache(tmp_path)
    wi = WikiIndex(tmp_path)
    assert wi.lookup("Biscuit Baron")["ns_name"] == "Main"
    assert wi.lookup("biscuit baron") is not None       # normalized
    hits = wi.search("gala grotesque", ns="RPlog")
    assert hits and hits[0]["title"] == "RPlog:Ghastly Gala"


def test_summary_for_rplog_and_article(tmp_path):
    _make_cache(tmp_path)
    wi = WikiIndex(tmp_path)
    # Article lead is read from the page file, markup + image + category stripped.
    blurb = wi.summary_for("Biscuit Baron")
    assert "fast-casual dining" in blurb
    assert "thumb" not in blurb and "File:" not in blurb and "Category" not in blurb


def test_logs_for_character_newest_first(tmp_path):
    _make_cache(tmp_path)
    wi = WikiIndex(tmp_path)
    logs = wi.logs_for_character("Cricket")
    assert [l["title"] for l in logs] == ["Charity Ball", "Ghastly Gala"]  # 34 ABY before 33
    assert logs[0]["summary"]


def test_topics_resolves_and_excludes(tmp_path):
    _make_cache(tmp_path)
    wi = WikiIndex(tmp_path)
    topics = wi.topics("tell me about the Biscuit Baron")
    assert any(t == "Biscuit Baron" for t, _ in topics)
    # exclude suppresses a covered name.
    assert wi.topics("tell me about the Biscuit Baron", exclude={"biscuit baron"}) == []


def test_shared_history(tmp_path):
    _make_cache(tmp_path)
    wi = WikiIndex(tmp_path)
    # Ghastly Gala has both Cricket and Zubindi -> shared.
    h = wi.shared_history(["Zubindi Hakoon"])
    assert h and h[0]["title"] == "Ghastly Gala" and h[0]["with"] == "Zubindi Hakoon"
    # Someone with no shared Cricket log -> nothing.
    assert wi.shared_history(["Nobody At All"]) == []


def test_missing_cache_graceful(tmp_path):
    wi = WikiIndex(tmp_path)  # empty dir
    assert not wi.loaded
    assert wi.lookup("x") is None
    assert wi.search("x") == []
    assert wi.summary_for("x") == ""
    assert wi.logs_for_character("Cricket") == []
    assert wi.topics("Biscuit Baron") == []
