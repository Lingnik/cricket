"""Memory accretion loop: !rp off summarizes + persists a scene; !rp on recalls it;
the next !pose seeds the recalled summary into the Turn."""

import asyncio
from types import SimpleNamespace

from cricket.auth import Level
from cricket.commands import builtins
from cricket.commands.registry import CommandContext
from cricket.memory.store import MemoryStore
from cricket.persona.base import BotIdentity, ContextLine, Response
from cricket.persona.stub import StubPersona

ROOM = "#0"


class SummarizerPersona:
    def __init__(self, summary="SCENE-SUMMARY"):
        self.summary = summary
        self.summarize_calls = []
        self.turns = []

    async def respond(self, turn):
        self.turns.append(turn)
        return Response(text="Cricket poses.", action="pose")

    async def summarize_scene(self, lines, cast=None):
        self.summarize_calls.append((list(lines), cast))
        return self.summary


class BarePersona:  # no summarize_scene capability
    async def respond(self, turn):
        return Response(text="x", action="pose")


class FakeActions:
    def __init__(self):
        self.calls = []

    def pose_room(self, text):
        self.calls.append(("pose_room", text))

    def emit_room(self, text):
        self.calls.append(("emit_room", text))

    def say_room(self, text):
        self.calls.append(("say_room", text))

    def page(self, target, text):
        self.calls.append(("page", target, text))


def make(persona, queue=None):
    bot = SimpleNamespace(
        current_room=ROOM,
        rp_enabled={},
        scene_queues={ROOM: list(queue or [])},
        persona=persona,
        store=MemoryStore(":memory:"),
        bot_identity=BotIdentity("Cricket", "#3"),
        actions=FakeActions(),
        locations={},
    )
    replies = []
    ctx = CommandContext(source="mush", level=Level.ADMIN, reply=replies.append, bot=bot)
    return bot, ctx, replies


def _q():
    return [
        ContextLine("Bazil", "#4", "pose", "strides into the hangar."),
        ContextLine("Bazil", "#4", "say", "Status report."),
    ]


def test_rp_off_summarizes_saves_and_clears():
    persona = SummarizerPersona("They argued; Cricket won.")
    bot, ctx, _ = make(persona, _q())
    asyncio.run(builtins.cmd_bang_rp(ctx, ["off"]))
    assert len(persona.summarize_calls) == 1
    assert persona.summarize_calls[0][1] == ["Bazil"]  # cast (bot excluded)
    assert bot.store.recall_scene_summary(ROOM) == "They argued; Cricket won."
    assert bot.scene_queues[ROOM] == []
    assert bot.rp_enabled[ROOM] is False


def test_rp_on_recalls_prior_scene():
    bot, ctx, replies = make(SummarizerPersona())
    bot.store.save_scene_summary(ROOM, ["Bazil"], "Last time, Bazil kicked him.")
    asyncio.run(builtins.cmd_bang_rp(ctx, ["on"]))
    assert bot.pending_recall[ROOM] == "Last time, Bazil kicked him."
    assert any("recalled" in r for r in replies)


def test_pose_seeds_recalled_summary():
    persona = SummarizerPersona()
    bot, ctx, _ = make(persona, _q())
    bot.pending_recall = {ROOM: "Bazil owes Cricket a taser."}
    asyncio.run(builtins.cmd_bang_pose(ctx, []))
    turn = persona.turns[0]
    assert turn.context[0].speaker == "memory"
    assert turn.context[0].text == "Earlier scene: Bazil owes Cricket a taser."
    # the real scene lines follow the recalled memory
    assert [c.speaker for c in turn.context[1:]] == ["Bazil", "Bazil"]


def test_stub_persona_end_to_end():
    bot, ctx, _ = make(StubPersona(), _q())
    asyncio.run(builtins.cmd_bang_rp(ctx, ["off"]))
    saved = bot.store.recall_scene_summary(ROOM)
    assert saved and "Bazil" in saved  # stub's trivial summary names the cast


def test_no_summarizer_clears_gracefully():
    bot, ctx, _ = make(BarePersona(), _q())
    asyncio.run(builtins.cmd_bang_rp(ctx, ["off"]))  # must not raise
    assert bot.scene_queues[ROOM] == []
    assert bot.rp_enabled[ROOM] is False
    assert bot.store.recall_scene_summary(ROOM) is None
