"""IC/OOC mode-aware lore scoping."""

from unittest.mock import MagicMock

from cricket.lore.loader import LoreStore
from cricket.persona.base import Turn
from cricket.persona.llm import LlmPersona


def _make_lore(tmp_path):
    d = tmp_path / "lore"
    (d / "dossiers").mkdir(parents=True)
    (d / "dossiers" / "atsvara-tarasar.md").write_text(
        "Atsvara is his partner-in-crime.\n\n"
        "## IC\nHe adores her in-scene and would burn the galaxy for her.\n\n"
        "## OOC\nMock her about the biscuit empire and her many shell companies.\n",
        encoding="utf-8",
    )
    (d / "dossiers" / "bob.md").write_text("Bob is a meatbag.", encoding="utf-8")
    (d / "index.json").write_text(
        '{"characters": {"Atsvara Tarasar": [], "Bob": []}}', encoding="utf-8"
    )
    return LoreStore(d)


def test_faceted_dossier_scopes(tmp_path):
    lore = _make_lore(tmp_path)
    ic = lore.retrieve(["Atsvara Tarasar"], scope="ic")
    ooc = lore.retrieve(["Atsvara Tarasar"], scope="ooc")
    assert "adores her in-scene" in ic
    assert "biscuit empire" not in ic  # OOC facet not leaked into IC
    assert "biscuit empire" in ooc
    assert "adores her in-scene" not in ooc
    assert "partner-in-crime" in ic and "partner-in-crime" in ooc  # shared preamble


def test_single_block_dossier_backward_compatible(tmp_path):
    lore = _make_lore(tmp_path)
    for scope in (None, "ic", "ooc"):
        assert "Bob is a meatbag" in lore.retrieve(["Bob"], scope=scope)


def test_llm_passes_scope_from_mode():
    lore = MagicMock()
    lore.retrieve.return_value = ""
    persona = LlmPersona(client=MagicMock(), lore=lore)
    rp_turn = Turn(
        mode="rp", location="#0", location_kind="room", directives="",
        speaker="Atsvara", speaker_dbref="#4", text="", context=[],
    )
    chat_turn = Turn(
        mode="chat", location="Lounge", location_kind="channel", directives="",
        speaker="Bob", speaker_dbref="#5", text="hi", context=[],
    )
    persona._retrieve_memories(rp_turn)
    persona._retrieve_memories(chat_turn)
    scopes = [c.kwargs.get("scope") for c in lore.retrieve.call_args_list]
    assert scopes == ["ic", "ooc"]
