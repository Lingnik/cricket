"""Tests for best-effort corpus-replay parsing."""

from __future__ import annotations

from evals import replay

SAMPLE_LOG = """== PAGE METADATA (do not summarize this header) ==
pageid: 471
title: RPlog:Sample
== RAW WIKITEXT ==
{{Rplog|author=[[Crestian Tarasar]]|date=[[33 ABY]]|title=Sample|synopsis=A test.}}

&nbsp;&nbsp;&nbsp;Atsvara strolls into the lockup and demands to see the droid.<br>

&nbsp;&nbsp;&nbsp;"I TAZED HIM!" come the furious electronic screams from the astromech [[Cricket]], who wheels around his cell. The droid's dome swivels with rage.

&nbsp;&nbsp;&nbsp;The constable sighs and rolls her eyes at the whole fiasco.
"""


def test_strip_markup_removes_cruft():
    out = replay.strip_markup(SAMPLE_LOG)
    assert "PAGE METADATA" not in out
    assert "Rplog" not in out
    assert "&nbsp;" not in out
    assert "[[" not in out
    assert "Cricket" in out


def test_paragraphs_split():
    paras = replay.paragraphs(SAMPLE_LOG)
    assert len(paras) >= 3
    assert any("TAZED" in p for p in paras)


def test_is_cricket_pose():
    paras = replay.paragraphs(SAMPLE_LOG)
    cricket = [p for p in paras if replay.is_cricket_pose(p)]
    assert any("astromech" in p for p in cricket)
    # the plain constable line is not a Cricket pose
    assert not replay.is_cricket_pose("The constable sighs and rolls her eyes.")


def test_make_replay_cases_from_dir(tmp_path):
    (tmp_path / "sample.txt").write_text(SAMPLE_LOG, encoding="utf-8")
    cases = replay.make_replay_cases(str(tmp_path))
    assert len(cases) == 1
    c = cases[0]
    assert c["mode"] == "rp"
    assert c["expect"]["action"] == "pose"
    assert "TAZED" in c["reference"]
    assert c["context"]  # scene-so-far captured
    assert "replay" in c["tags"]


def test_missing_dir_returns_empty():
    assert replay.make_replay_cases("") == []
    assert replay.make_replay_cases("/no/such/path/xyz") == []
