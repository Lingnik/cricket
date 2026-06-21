"""Tests for the goal-aligned eval harness (no model needed)."""

from __future__ import annotations

from evals.goals import load_cases, run, turn_for


class _FakePersona:
    async def respond(self, turn):
        class R:
            text = "*zot* fine."
            action = "say"
        return R()


def test_cases_load_and_shape():
    cases = load_cases()
    assert len(cases) >= 15
    assert all("id" in c and "kind" in c and "mode" in c for c in cases)
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))  # unique ids


def test_turn_for_chat_and_rp():
    chat = turn_for({"mode": "chat", "text": "hi"})
    assert chat.mode == "chat" and chat.text == "hi"
    rp = turn_for({"mode": "rp", "scene": ["one", "two"]})
    assert rp.mode == "rp" and [c.text for c in rp.context] == ["one", "two"]


def test_run_collects_outputs():
    rows = run([{"id": "x", "kind": "k", "mode": "chat", "text": "q"}], _FakePersona())
    assert rows[0]["id"] == "x" and rows[0]["gen_new"] == "*zot* fine."
    assert "gen_base" not in rows[0]


def test_run_base_ab():
    rows = run([{"id": "x", "kind": "k", "mode": "chat", "text": "q"}],
               _FakePersona(), _FakePersona())
    assert "gen_base" in rows[0]
