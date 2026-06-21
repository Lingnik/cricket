"""Tests for the pluggable judge."""

from __future__ import annotations

from evals import judge as judge_mod


class Out:
    def __init__(self, text, action="say"):
        self.text = text
        self.action = action


def test_null_judge_skips():
    res = judge_mod.NullJudge().score({}, Out("x"))
    assert res["dimensions"] == {d: None for d in judge_mod.DIMENSIONS}
    assert "skip" in res["rationale"].lower()


def test_prompt_bundle_renders_rubric_and_output():
    case = {
        "mode": "chat", "location": "Public", "location_kind": "channel",
        "directives": "Keep it PG.", "cast": ["Bob"], "text": "hello cricket",
    }
    j = judge_mod.PromptBundleJudge(voice_anchor="BEEP BOOP I AM CRICKET")
    rendered = j.render(case, Out("BZZT. Hello."))
    assert "in_character" in rendered
    assert "Keep it PG." in rendered
    assert "BZZT. Hello." in rendered
    assert "BEEP BOOP I AM CRICKET" in rendered


def test_prompt_bundle_includes_reference_when_present():
    case = {"mode": "rp", "reference": "HNNNNGGHHHH the astromech rages"}
    rendered = judge_mod.PromptBundleJudge().render(case, Out("beep", "pose"))
    assert "GROUND-TRUTH" in rendered
    assert "HNNNNGGHHHH" in rendered


def test_bundle_score_returns_prompt_and_empty_dims():
    res = judge_mod.PromptBundleJudge().score({"mode": "chat"}, Out("x"))
    assert "prompt" in res
    assert all(v is None for v in res["dimensions"].values())
