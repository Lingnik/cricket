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


PRECISION_LOG = """== RAW WIKITEXT ==
{{Rplog|title=Precision}}

&nbsp;"Where is that infernal droid?" Atsvara demands of the constable, glancing at [[Cricket]]'s empty cell.<br>

&nbsp;"FILTHY MEATBAGS!" Cricket shrieks, his dome spinning with rage as he wheels forward at the bars.<br>

&nbsp;The constable shrugs and mutters something about the astromech being someone else's problem entirely.<br>

&nbsp;"HNNNGH," the astromech replies, lying on the floor and spinning his wheels fruitlessly in the air.
"""


def test_only_cricket_led_paragraphs_are_poses():
    poses = [p for p in replay.paragraphs(PRECISION_LOG) if replay.is_cricket_pose(p)]
    # Cricket is the SPEAKER/actor here -> poses.
    assert any("FILTHY MEATBAGS" in p for p in poses)
    assert any("HNNNGH" in p for p in poses)
    # These only REFERENCE him (Atsvara's line, the constable's line) -> not poses.
    assert not any("Atsvara demands" in p for p in poses)
    assert not any("constable shrugs" in p for p in poses)
    assert len(poses) == 2


def test_addressee_mention_is_not_a_pose():
    # "to Cricket" (addressee), not "Cricket <verb>" (speaker) -- must be rejected.
    assert not replay.is_cricket_pose(
        '"Calm down," she says soothingly to Cricket, patting his dome plating gently.'
    )


def test_min_length_guard():
    assert not replay.is_cricket_pose("Cricket.")


def test_log_year_parsing():
    assert replay._log_year("2024 - Ghastly Gala.txt") == 2024
    assert replay._log_year("2006-02 - Battle.txt") == 2006
    assert replay._log_year("Untitled.txt") is None


def test_min_year_filters_old_logs(tmp_path):
    (tmp_path / "2006-02 - Old.txt").write_text(SAMPLE_LOG, encoding="utf-8")
    (tmp_path / "2024 - New.txt").write_text(SAMPLE_LOG, encoding="utf-8")
    # No filter: both logs contribute.
    all_cases = replay.make_replay_cases(str(tmp_path), min_year=None)
    assert any("2006" in c["id"] for c in all_cases)
    assert any("2024" in c["id"] for c in all_cases)
    # min_year=2023: the 2006 log is excluded, the 2024 log kept.
    recent = replay.make_replay_cases(str(tmp_path), min_year=2023)
    assert recent, "expected at least one recent case"
    assert all("2006" not in c["id"] for c in recent)
    assert any("2024" in c["id"] for c in recent)
