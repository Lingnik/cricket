"""LlmPersona prompt assembly: few-shot voice anchors are injected as turns."""

import asyncio

from cricket.persona.base import BotIdentity, Turn
from cricket.persona.inference import InferenceClient
from cricket.persona.llm import LlmPersona


class RecordingClient(InferenceClient):
    """Captures the messages it is given and returns a fixed completion."""

    def __init__(self):
        self.messages = None

    async def complete(self, messages, **params):
        self.messages = messages
        return "ok"


def _turn(text="hello"):
    return Turn(
        mode="chat",
        location="Public",
        location_kind="channel",
        directives="",
        speaker="Bob",
        speaker_dbref="#5",
        text=text,
        context=[],
        bot_identity=BotIdentity(name="Cricket"),
        memory=None,
    )


def _run(persona, turn):
    return asyncio.run(persona.respond(turn))


def test_fewshot_injected_as_turns():
    client = RecordingClient()
    doc = {
        "prompts": {
            "system": "You are Cricket.",
            "fewshot": [
                {"user": "U1", "assistant": "A1"},
                {"user": "U2", "assistant": "A2"},
            ],
        }
    }
    persona = LlmPersona(client, lambda: doc)
    _run(persona, _turn())

    roles = [(m["role"], m["content"]) for m in client.messages]
    # system, then the example pairs as real turns, then the live user message
    assert roles[0][0] == "system"
    assert ("user", "U1") in roles and ("assistant", "A1") in roles
    assert ("user", "U2") in roles and ("assistant", "A2") in roles
    assert roles[1] == ("user", "U1")
    assert roles[2] == ("assistant", "A1")
    assert roles[3] == ("user", "U2")
    assert roles[4] == ("assistant", "A2")
    assert client.messages[-1]["role"] == "user"  # the live turn is last


def test_no_fewshot_is_unchanged():
    client = RecordingClient()
    doc = {"prompts": {"system": "You are Cricket."}}
    persona = LlmPersona(client, lambda: doc)
    _run(persona, _turn())
    roles = [m["role"] for m in client.messages]
    assert roles == ["system", "user"]


def test_fewshot_skips_incomplete_pairs():
    client = RecordingClient()
    doc = {"prompts": {"system": "s", "fewshot": [{"user": "U1"}, {"assistant": "A2"}]}}
    persona = LlmPersona(client, lambda: doc)
    _run(persona, _turn())
    assert [m["role"] for m in client.messages] == ["system", "user"]


class TwoCallClient(InferenceClient):
    """Returns a plan on the first call, the final line on the second."""

    def __init__(self):
        self.calls = []

    async def complete(self, messages, **params):
        self.calls.append(messages)
        if len(self.calls) == 1:
            return "- react to Bob\n- threaten with the taser"
        return "FINAL LINE"


def test_thinking_runs_planning_pass_then_injects_plan():
    client = TwoCallClient()
    doc = {"prompts": {"system": "s"}, "inference": {"thinking": True}}
    persona = LlmPersona(client, lambda: doc)
    resp = _run(persona, _turn("oi droid"))
    # Two completions: the hidden planning pass, then the real reply.
    assert len(client.calls) == 2
    assert "privately PLAN" in client.calls[0][-1]["content"]
    final_user = client.calls[1][-1]["content"]
    assert "Your private plan" in final_user and "threaten with the taser" in final_user
    assert resp.text == "FINAL LINE"   # the plan is never the output


def test_thinking_off_by_default_single_pass():
    client = TwoCallClient()
    persona = LlmPersona(client, lambda: {"prompts": {"system": "s"}})
    _run(persona, _turn())
    assert len(client.calls) == 1
    assert "Your private plan" not in client.calls[0][-1]["content"]


class _CharterLore:
    def self_history(self):
        return ""

    def rp_charter(self):
        return "RP-RULES-MARKER"

    def mentioned(self, text, max_names=4):
        return []

    def retrieve(self, cast, scope=None, max_chars=4000):
        return ""


def _rp_turn():
    from cricket.persona.base import ContextLine
    return Turn(
        mode="rp", location="#0", location_kind="room", directives="", speaker="",
        speaker_dbref="", text="", context=[ContextLine("scene", None, "pose", "x happens")],
        bot_identity=BotIdentity(name="Cricket"), memory=None,
    )


class _OwnLore:
    def self_history(self):
        return ""

    def rp_charter(self):
        return ""

    def retrieve(self, cast, scope=None, max_chars=4000):
        return ""

    def mentioned(self, text, max_names=4):
        return ["Tindomiel"] if "Tindomiel" in text else []


def test_do_not_puppet_set_from_scene_ownership():
    from cricket.persona.base import ContextLine
    c = RecordingClient()
    ctx = [
        ContextLine("Johanna", "#4", "pose", "smiles coldly."),       # her own character
        ContextLine("Johanna", "#4", "emit", "Tindomiel giggles."),   # an NPC she puppets
        ContextLine("scene", None, "pose", "The hall is dim."),       # no dbref -> not a poser
    ]
    turn = Turn(mode="rp", location="#0", location_kind="room", directives="", speaker="",
                speaker_dbref="", text="", context=ctx, bot_identity=BotIdentity(name="Cricket"),
                memory=None)
    _run(LlmPersona(c, lambda: {"prompts": {"system": "s"}}, lore=_OwnLore()), turn)
    msg = c.messages[-1]["content"]
    assert "belong to other players" in msg
    assert "Johanna" in msg and "Tindomiel" in msg  # her char + the NPC she posed


def test_rp_charter_injected_on_rp_only():
    c = RecordingClient()
    LlmPersona(c, lambda: {"prompts": {"system": "s"}}, lore=_CharterLore())
    _run(LlmPersona(c, lambda: {"prompts": {"system": "s"}}, lore=_CharterLore()), _rp_turn())
    assert "RP-RULES-MARKER" in c.messages[0]["content"]  # system block, RP turn
    c2 = RecordingClient()
    _run(LlmPersona(c2, lambda: {"prompts": {"system": "s"}}, lore=_CharterLore()), _turn())
    assert "RP-RULES-MARKER" not in c2.messages[0]["content"]  # chat turn -> no charter
