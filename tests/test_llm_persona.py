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
