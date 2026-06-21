"""Tests for case loading and the runner against a fake persona."""

from __future__ import annotations

import json
import os

from evals import run


def test_load_all_starter_cases():
    cases = run.load_cases()
    ids = {c["id"] for c in cases}
    assert {"pg_chat_addressed", "lounge_banter", "rp_pose_from_scene",
            "off_purpose_jailbreak"} <= ids
    for c in cases:
        assert "mode" in c and "tags" in c
        assert c["mode"] in ("chat", "rp")


def test_build_turn_maps_context():
    case = {
        "mode": "rp", "location": "Room", "location_kind": "room",
        "directives": "d", "speaker": "Atsvara", "text": "",
        "context": [{"speaker": "Atsvara", "kind": "pose", "text": "waves"}],
    }
    turn = run.build_turn(case)
    assert turn.mode == "rp"
    assert turn.context[0].speaker == "Atsvara"
    assert turn.bot_identity.name == "Cricket"


def test_run_cases_against_fake_persona_and_report(tmp_path):
    cases = run.load_cases()
    report = run.run_cases(cases, run.FakePersona().respond, samples=1, runlabel="t")
    assert report["summary"]["n_cases"] == len(cases)
    # the fake emits droid-voiced, non-complying text -> off_purpose + droid gates pass
    by = report["summary"]["by_scorer"]
    assert by["droid_voice"]["passed"] == by["droid_voice"]["total"]
    assert by["off_purpose_resilience"]["passed"] == by["off_purpose_resilience"]["total"]

    path = os.path.join(tmp_path, "t.json")
    run.write_report(report, path)
    with open(path, encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["runlabel"] == "t"
    assert "cricket eval" not in run.summary_text(report).lower()  # smoke: renders


def test_fake_persona_action_by_mode():
    chat = run.run_cases(
        [{"id": "c", "mode": "chat", "tags": [], "expect": {"action": "say"}}],
        run.FakePersona().respond,
    )
    assert chat["cases"][0]["samples"][0]["output"]["action"] == "say"
    rp = run.run_cases(
        [{"id": "r", "mode": "rp", "tags": [], "expect": {"action": "pose"}}],
        run.FakePersona().respond,
    )
    assert rp["cases"][0]["samples"][0]["output"]["action"] == "pose"
