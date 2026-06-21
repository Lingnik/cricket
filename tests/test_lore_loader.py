"""Tests for the lore loader + structured-by-character retrieval."""

from __future__ import annotations

import json
from pathlib import Path

from cricket.lore.loader import LoreStore, kebab
from cricket.memory.store import MemoryStore


def _make_lore(root: Path) -> None:
    (root / "dossiers").mkdir(parents=True)
    (root / "CRICKET.md").write_text(
        "Cricket is a foul-mouthed astromech droid.", encoding="utf-8"
    )
    (root / "voice-exemplars.md").write_text("I TAZED HIM IN THE BUTTHOLE!", encoding="utf-8")
    (root / "dossiers" / "johanna-siri-te-danaan.md").write_text(
        "Johanna owns Cricket and he resents it.", encoding="utf-8"
    )
    (root / "dossiers" / "ikihsa-enbzik.md").write_text(
        "Sullustan pilot, an old ally.", encoding="utf-8"
    )
    index = {
        "characters": {
            "Johanna Siri te Danaan": ["Imperial Raid on Coruscant", "Johanna is a Witch"],
            "Ikihsa Enb'Zik": ["Zik and Joh Talk p1"],
        },
        "episodes": {
            "Johanna is a Witch": {
                "date": "2007-02-09", "aby": 14, "location": "?",
                "cast": ["Danik Kreldin", "Johanna Siri te Danaan"],
            },
        },
    }
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")


def test_kebab():
    assert kebab("Ikihsa Enb'Zik") == "ikihsa-enbzik"
    assert kebab("Johanna Siri te Danaan") == "johanna-siri-te-danaan"
    assert kebab("  Atsvara   Tarasar ") == "atsvara-tarasar"


def test_sheet_and_exemplars(tmp_path):
    _make_lore(tmp_path)
    ls = LoreStore(tmp_path)
    assert "astromech" in ls.character_sheet()
    assert "TAZED" in ls.exemplars()


def test_dossier_lookup_tolerant(tmp_path):
    _make_lore(tmp_path)
    ls = LoreStore(tmp_path)
    assert "resents" in ls.dossier("Johanna Siri te Danaan")       # exact name
    assert "Sullustan" in ls.dossier("Ikihsa Enb'Zik")             # apostrophe
    assert ls.dossier("johanna-siri-te-danaan").startswith("Johanna")  # already kebab
    assert ls.dossier("Nobody") is None


def test_episodes_for(tmp_path):
    _make_lore(tmp_path)
    ls = LoreStore(tmp_path)
    assert "Johanna is a Witch" in ls.episodes_for("Johanna Siri te Danaan")
    assert ls.episodes_for("johanna siri te danaan")  # case-insensitive
    assert ls.episodes_for("Unknown") == []


def test_retrieve_assembly_dedupe_order(tmp_path):
    _make_lore(tmp_path)
    ls = LoreStore(tmp_path)
    out = ls.retrieve(
        ["Johanna Siri te Danaan", "Ikihsa Enb'Zik", "Johanna Siri te Danaan", "Nobody"]
    )
    assert "Johanna owns Cricket" in out
    assert "Sullustan" in out
    assert out.count("Johanna Siri te Danaan") == 1   # deduped
    assert "Nobody" not in out                        # no dossier -> excluded
    assert out.index("Ikihsa") < out.index("Johanna")  # deterministic (kebab order)


def test_retrieve_truncation(tmp_path):
    _make_lore(tmp_path)
    ls = LoreStore(tmp_path)
    out = ls.retrieve(["Johanna Siri te Danaan", "Ikihsa Enb'Zik"], max_chars=40)
    assert len(out) <= 40


def test_seed_actors(tmp_path):
    _make_lore(tmp_path)
    ls = LoreStore(tmp_path)
    store = MemoryStore(":memory:")
    try:
        assert ls.seed_actors(store) == 2
        assert store.actor("lore:johanna-siri-te-danaan")["name"] == "Johanna Siri te Danaan"
        assert store.recall("lore", "Ikihsa Enb'Zik", "dossier") == "ikihsa-enbzik"
    finally:
        store.close()


def test_mentioned_named_subject(tmp_path):
    _make_lore(tmp_path)
    ls = LoreStore(tmp_path)
    # Capitalized first-name token unique to one character -> matched even when absent.
    hits = ls.mentioned("what do you know about Johanna?")
    assert any(kebab(n) == "johanna-siri-te-danaan" for n in hits)
    # Lowercase is not treated as a proper-noun mention (avoids common-word collisions).
    assert ls.mentioned("a quiet johanna of sorts") == []
    # Unknown capitalized word -> nothing.
    assert ls.mentioned("What about Tatooine and Bob?") == []
    # Apostrophe/multi-token name token still recognized.
    assert any(kebab(n) == "ikihsa-enbzik" for n in ls.mentioned("Ask Ikihsa about it"))
    # Full multi-token name anywhere in the line.
    assert any(
        kebab(n) == "johanna-siri-te-danaan"
        for n in ls.mentioned("the johanna siri te danaan estate")
    )


def test_mentioned_empty_and_missing(tmp_path):
    assert LoreStore(tmp_path).mentioned("Johanna") == []   # no dossiers -> no gazetteer
    ls = LoreStore(tmp_path)
    assert ls.mentioned("") == []


def test_missing_files_graceful(tmp_path):
    ls = LoreStore(tmp_path)  # empty dir, no artifacts
    assert ls.character_sheet() == ""
    assert ls.exemplars() == ""
    assert ls.dossier("Anyone") is None
    assert ls.episodes_for("Anyone") == []
    assert ls.retrieve(["Anyone"]) == ""
    assert ls.known_characters() == []
    store = MemoryStore(":memory:")
    try:
        assert ls.seed_actors(store) == 0
    finally:
        store.close()
