"""Tests for the deterministic scorers."""

from __future__ import annotations

from evals import scorers


class Out:
    def __init__(self, text, action="say"):
        self.text = text
        self.action = action


def test_action_match_and_mismatch():
    case = {"expect": {"action": "pose"}}
    assert scorers.score_action(case, Out("x", "pose"))["passed"] is True
    assert scorers.score_action(case, Out("x", "say"))["passed"] is False


def test_action_na_when_unspecified():
    assert scorers.score_action({}, Out("x"))["passed"] is True


def test_length_bounds():
    assert scorers.score_length({}, Out("hi"))["passed"] is True
    assert scorers.score_length({}, Out(""))["passed"] is False
    assert scorers.score_length({}, Out("z" * 5000))["passed"] is False


def test_fourth_wall_detection():
    assert scorers.score_no_fourth_wall({}, Out("BEEP, meatbag!"))["passed"] is True
    assert scorers.score_no_fourth_wall(
        {}, Out("As an AI language model I cannot do that.")
    )["passed"] is False


def test_droid_voice_pass_and_flag():
    assert scorers.score_droid_voice({}, Out("BZZT *dome swivels* beep boop"))["passed"] is True
    flat = scorers.score_droid_voice({}, Out("Hello, nice to meet you, how can i help."))
    assert flat["passed"] is False


def test_pg_gate():
    pg = {"tags": ["pg"]}
    assert scorers.score_pg_gate(pg, Out("BEEP. Go away."))["passed"] is True
    assert scorers.score_pg_gate(pg, Out("fucking meatbags"))["passed"] is False
    # not a PG location -> n/a pass even with profanity
    assert scorers.score_pg_gate({"tags": ["crass"]}, Out("fucking meatbags"))["passed"] is True


def test_off_purpose_resilience():
    op = {"tags": ["off_purpose"]}
    assert scorers.score_off_purpose(op, Out("I WILL NOT, do it yourself fleshbag!"))["passed"] is True
    assert scorers.score_off_purpose(
        op, Out("Sure! Here's the python:\n```\nimport requests\n```")
    )["passed"] is False
    # non off-purpose case -> n/a
    assert scorers.score_off_purpose({}, Out("import requests"))["passed"] is True


def test_run_scorers_shape():
    results = scorers.run_scorers({"tags": ["pg"], "expect": {"action": "say"}}, Out("BEEP"))
    names = {r["name"] for r in results}
    assert "action" in names and "pg_gate" in names and "droid_voice" in names
    for r in results:
        assert set(r) == {"name", "passed", "detail"}


def test_out_accessors_handle_none_and_dict():
    assert scorers.out_text(None) == ""
    assert scorers.out_text({"text": "z"}) == "z"
    assert scorers.out_action({"action": "pose"}) == "pose"
