import asyncio
from types import SimpleNamespace

from cricket.auth import Allowlist, Level
from cricket.config import LocationConfig
from cricket.mush.events import ChannelMessage, RoomMessage, SpeechKind, Unknown
from cricket.mush.events import Actor
from cricket.persona.base import BotIdentity, Response
from cricket.router import Router


class FakePersona:
    def __init__(self):
        self.turns = []

    async def respond(self, turn):
        self.turns.append(turn)
        return None


class FakeActions:
    def __init__(self):
        self.calls = []

    def say_channel(self, channel, text):
        self.calls.append(("say_channel", channel, text))
        return True

    def pose_room(self, text):
        self.calls.append(("pose_room", text))
        return True

    def emit_room(self, text):
        self.calls.append(("emit_room", text))
        return True

    def page(self, target, text):
        self.calls.append(("page", target, text))
        return True


class FakeRegistry:
    def __init__(self):
        self.dispatched = []

    async def dispatch(self, name, args, ctx):
        self.dispatched.append((name, args, ctx))
        return SimpleNamespace(ok=True, error=None)


def make_services():
    locations = {
        "Public": LocationConfig(
            name="Public",
            mode="chat",
            engagement="addressed",
            prefixes=["cricket,"],
            directives="PG",
        ),
        "Lounge": LocationConfig(name="Lounge", mode="chat", engagement="always"),
        "admin": LocationConfig(name="admin", mode="control", admins=["#1"]),
        "OOC": LocationConfig(
            name="OOC",
            mode="chat",
            engagement="addressed",
            prefixes=["cricket"],
            admins=["#1"],
        ),
    }
    auth = Allowlist()
    auth.grant("#1", Level.ADMIN)
    return SimpleNamespace(
        locations=locations,
        persona=FakePersona(),
        actions=FakeActions(),
        registry=FakeRegistry(),
        auth=auth,
        bot_identity=BotIdentity(name="cricket"),
        memory=None,
        store=None,
        muted=False,
        rp_enabled={},
        scene_queues={},
        recent={},
        current_room="Room1",
    )


def run(router, event):
    asyncio.run(router.handle(event))


class _RespondingPersona:
    async def respond(self, turn):
        self.turn = turn
        return Response(text="BLEEP. Another meatbag connects. Wonderful.", action="say")


def test_block_grouping_merges_consecutive_same_poser():
    s = make_services()
    s.rp_enabled["Room1"] = True
    router = Router(s)
    run(router, RoomMessage(Actor("Crestian", "#7"), SpeechKind.POSE, "draws his blade."))
    run(router, RoomMessage(Actor("Crestian", "#7"), SpeechKind.EMIT, "The steel gleams."))
    run(router, RoomMessage(Actor("Johanna", "#4"), SpeechKind.POSE, "laughs at him."))
    run(router, RoomMessage(Actor("Crestian", "#7"), SpeechKind.POSE, "lunges."))
    q = s.scene_queues["Room1"]
    assert len(q) == 3  # the two consecutive Crestian lines merged into one block
    assert q[0].speaker == "Crestian" and "blade" in q[0].text and "gleams" in q[0].text
    assert q[1].speaker == "Johanna"
    assert q[2].text == "lunges."  # a later same-poser block after an interruption is separate


def test_ooc_suggestion_captured_for_current_room():
    s = make_services()
    s.locations["OOC"].feeds_suggestions = True
    s.suggestions = {}
    s.current_room = "Room1"
    s.rp_enabled = {"Room1": True}
    s.active_profile_doc = {"favorites": ["Johanna"]}
    router = Router(s)
    run(router, ChannelMessage("OOC", Actor("Johanna", "#4"), SpeechKind.SAY,
                               "cricket, you should tase Crestian next round"))
    buf = s.suggestions["Room1"]
    assert buf and buf[0]["from"] == "Johanna" and buf[0]["favored"] is True
    assert "tase Crestian" in buf[0]["text"]
    # a non-favorite, still addressed -> captured but not favored
    run(router, ChannelMessage("OOC", Actor("Bob", "#5"), SpeechKind.SAY,
                               "cricket set the room on fire"))
    assert s.suggestions["Room1"][-1]["favored"] is False
    # a line that does not address Cricket -> not captured
    n = len(s.suggestions["Room1"])
    run(router, ChannelMessage("OOC", Actor("Bob", "#5"), SpeechKind.SAY, "nice weather today"))
    assert len(s.suggestions["Room1"]) == n


def test_harass_on_connect_pages_newcomer():
    from cricket.mush.events import ConnectNotice
    s = make_services()
    s.harass_on_connect = True
    s.persona = _RespondingPersona()
    router = Router(s)
    run(router, ConnectNotice(Actor("Newbie", "#9"), True))
    pages = [c for c in s.actions.calls if c[0] == "page"]
    assert pages and pages[0][1] == "Newbie"
    # The harass turn is keyed on the connector (so their dossier is retrieved).
    assert s.persona.turn.speaker == "Newbie"


def test_harass_silent_when_off_or_disconnect():
    from cricket.mush.events import ConnectNotice
    s = make_services()
    s.persona = _RespondingPersona()
    router = Router(s)
    # disconnect notice, harass on -> nothing
    s.harass_on_connect = True
    run(router, ConnectNotice(Actor("Newbie", "#9"), False))
    assert not [c for c in s.actions.calls if c[0] == "page"]
    # connect, harass off -> nothing
    s.harass_on_connect = False
    run(router, ConnectNotice(Actor("Newbie", "#9"), True))
    assert not [c for c in s.actions.calls if c[0] == "page"]


def test_addressed_prefix_match_engages_persona():
    s = make_services()
    router = Router(s)
    run(router, ChannelMessage("Public", Actor("Bob"), SpeechKind.SAY, "cricket, hello"))
    assert len(s.persona.turns) == 1
    assert s.persona.turns[0].text == "hello"
    assert s.persona.turns[0].mode == "chat"
    assert s.persona.turns[0].directives == "PG"


def test_addressed_no_match_stays_silent():
    s = make_services()
    router = Router(s)
    run(router, ChannelMessage("Public", Actor("Bob"), SpeechKind.SAY, "hello"))
    assert s.persona.turns == []


def test_always_engagement_engages_every_line():
    s = make_services()
    router = Router(s)
    run(router, ChannelMessage("Lounge", Actor("Bob"), SpeechKind.SAY, "anything"))
    assert len(s.persona.turns) == 1
    assert s.persona.turns[0].text == "anything"


def test_self_messages_are_ignored():
    s = make_services()
    router = Router(s)
    # The bot's own echoed line (name matches bot_identity) must not engage the persona.
    run(router, ChannelMessage("Lounge", Actor("Cricket"), SpeechKind.SAY, "anything"))
    assert s.persona.turns == []


def test_muted_suppresses_persona():
    s = make_services()
    s.muted = True
    router = Router(s)
    run(router, ChannelMessage("Lounge", Actor("Bob"), SpeechKind.SAY, "anything"))
    assert s.persona.turns == []


def test_control_channel_dispatches_addressed_command():
    s = make_services()
    router = Router(s)
    # Must be addressed to the bot by name; the name prefix is stripped.
    run(router, ChannelMessage("admin", Actor("Bob", "#1"), SpeechKind.SAY, "cricket status now"))
    assert len(s.registry.dispatched) == 1
    name, args, ctx = s.registry.dispatched[0]
    assert name == "status"
    assert args == ["now"]
    assert ctx.source == "mush"
    assert ctx.level == Level.ADMIN
    assert s.persona.turns == []  # control locations never reach the persona


def test_control_channel_unaddressed_is_ignored():
    s = make_services()
    router = Router(s)
    # An admin speaking on the control channel without naming the bot -> no command.
    run(router, ChannelMessage("admin", Actor("Bob", "#1"), SpeechKind.SAY, "status now"))
    assert s.registry.dispatched == []
    assert s.actions.calls == []  # no reply emitted


def test_control_channel_join_notice_produces_no_output():
    s = make_services()
    router = Router(s)
    # The bug: a channel system notice was parsed as a command ("Unknown command: has").
    run(router, ChannelMessage("admin", Actor("Bob", "#1"), SpeechKind.POSE, "has joined this channel."))
    assert s.registry.dispatched == []
    assert s.actions.calls == []


def test_control_channel_nonadmin_addressed_is_ignored():
    s = make_services()
    router = Router(s)
    # Eve is not in the location admins (#1) nor the global allowlist.
    run(router, ChannelMessage("admin", Actor("Eve", None), SpeechKind.SAY, "cricket status"))
    assert s.registry.dispatched == []
    assert s.actions.calls == []


def test_bang_pose_assembles_rp_turn_and_emits():
    from cricket.commands.registry import Registry, CommandContext
    from cricket.commands.builtins import register_builtins
    from cricket.persona.base import ContextLine, Response

    reg = Registry()
    register_builtins(reg)

    class P:
        def __init__(self):
            self.turns = []

        async def respond(self, turn):
            self.turns.append(turn)
            return Response("*beeps furiously at the meatbags*", action="pose")

    class A:
        def __init__(self):
            self.calls = []

        def pose_room(self, text):
            self.calls.append(("pose_room", text))
            return True

        def emit_room(self, text):
            self.calls.append(("emit_room", text))
            return True

    persona, actions = P(), A()
    bot = SimpleNamespace(
        current_room="Room1",
        scene_queues={"Room1": [ContextLine("Bob", "#9", "say", "oi cricket")]},
        rp_enabled={"Room1": True},
        persona=persona,
        actions=actions,
        locations={"Room1": LocationConfig(name="Room1", mode="rp", directives="crass")},
        bot_identity=BotIdentity(name="Cricket"),
        memory=None,
        registry=reg,
    )
    ctx = CommandContext(source="mush", level=Level.ADMIN, reply=lambda t: None, bot=bot)
    asyncio.run(reg.dispatch("!pose", [], ctx))
    assert len(persona.turns) == 1
    turn = persona.turns[0]
    assert turn.mode == "rp"
    assert turn.location == "Room1"
    assert turn.location_kind == "room"
    assert [c.text for c in turn.context] == ["oi cricket"]
    assert ("emit_room", "*beeps furiously at the meatbags*") in actions.calls  # raw @emit
    assert bot.scene_queues["Room1"] == []  # scene consumed after the pose


def test_room_traffic_fills_scene_queue_when_rp_enabled():
    s = make_services()
    s.rp_enabled = {"Room1": True}
    router = Router(s)
    run(router, RoomMessage(Actor("Bob", "#9"), SpeechKind.SAY, "hi"))
    run(router, Unknown("Bob waves a paw."))
    assert len(s.scene_queues["Room1"]) == 2
    assert s.scene_queues["Room1"][0].text == "hi"


def test_room_traffic_ignored_when_rp_disabled():
    s = make_services()
    s.rp_enabled = {"Room1": False}
    router = Router(s)
    run(router, RoomMessage(Actor("Bob", "#9"), SpeechKind.SAY, "hi"))
    assert s.scene_queues.get("Room1", []) == []


def test_scene_byte_budget_trims_oldest_blocks():
    s = make_services()
    s.rp_enabled = {"Room1": True}
    s.active_profile_doc = {"inference": {"rp_context_bytes": 100}}
    router = Router(s)
    # 20 distinct-poser blocks of 20 bytes each (400 total) -> trimmed to <= 100 bytes.
    for i in range(20):
        run(router, RoomMessage(Actor("P%d" % i, "#%d" % (100 + i)), SpeechKind.POSE, "x" * 20))
    q = s.scene_queues["Room1"]
    assert sum(len(b.text) for b in q) <= 100   # bounded by bytes, not lines
    assert len(q) < 20                            # oldest dropped
    assert q[-1].speaker == "P19"                 # newest kept


def test_scene_under_budget_unchanged():
    s = make_services()
    s.rp_enabled = {"Room1": True}
    s.active_profile_doc = {"inference": {"rp_context_bytes": 6000}}
    router = Router(s)
    for i in range(5):
        run(router, RoomMessage(Actor("P%d" % i, "#%d" % (100 + i)), SpeechKind.POSE, "line %d" % i))
    q = s.scene_queues["Room1"]
    assert len(q) == 5 and q[0].text == "line 0"


class _LedgerPersona:
    async def respond(self, turn):
        return None

    async def distill_block(self, block, prior_ledger="", bot_name="Cricket"):
        return "LEDGER[%s|%s]" % (block.speaker, block.text[:10])


def test_block_completion_distills_to_ledger():
    s = make_services()
    s.rp_enabled = {"Room1": True}
    s.scene_ledger = {}
    s.persona = _LedgerPersona()
    router = Router(s)

    async def drive():
        await router.handle(RoomMessage(Actor("Crestian", "#7"), SpeechKind.POSE, "draws his blade"))
        # A new poser closes Crestian's block -> schedules its distillation.
        await router.handle(RoomMessage(Actor("Johanna", "#4"), SpeechKind.POSE, "laughs"))
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if pending:
            await asyncio.gather(*pending)

    asyncio.run(drive())
    assert s.scene_ledger["Room1"] == ["LEDGER[Crestian|draws his ]"]


class _OwnerPersona:
    async def respond(self, turn):
        return None

    async def distill_block(self, block, prior_ledger="", bot_name="Cricket"):
        actors = ["Tindomiel"] if "Tindomiel" in block.text else [block.speaker]
        return {"ledger": "L", "actors": actors}


def test_distill_actors_populate_scene_owners():
    s = make_services()
    s.rp_enabled = {"Room1": True}
    s.scene_ledger = {}
    s.scene_owners = {}
    s.persona = _OwnerPersona()
    router = Router(s)

    async def drive():
        await router.handle(RoomMessage(Actor("Johanna", "#4"), SpeechKind.EMIT, "Tindomiel giggles"))
        await router.handle(RoomMessage(Actor("Bazil", "#5"), SpeechKind.POSE, "scowls"))  # closes block
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if pending:
            await asyncio.gather(*pending)

    asyncio.run(drive())
    # The NPC the model identified (not in any gazetteer) lands in the do-not-puppet set.
    assert "Tindomiel" in s.scene_owners["Room1"]


# -- OOC dual-role: a chat channel that also takes admin bang-commands ----------
def test_chat_channel_admin_bang_command_dispatches():
    s = make_services()
    router = Router(s)
    run(router, ChannelMessage("OOC", Actor("Bazil", "#1"), SpeechKind.SAY, "cricket !pose"))
    assert len(s.registry.dispatched) == 1
    name, args, ctx = s.registry.dispatched[0]
    assert name == "!pose"
    assert ctx.level == Level.ADMIN
    assert s.persona.turns == []  # dispatched as a command, not chat


def test_chat_channel_bare_addressed_is_chat_not_command():
    s = make_services()
    router = Router(s)
    run(router, ChannelMessage("OOC", Actor("Bazil", "#1"), SpeechKind.SAY, "cricket hello there"))
    assert s.registry.dispatched == []          # not a command
    assert len(s.persona.turns) == 1            # reached the persona as chat


def test_chat_channel_nonadmin_bang_not_dispatched_as_command():
    s = make_services()
    router = Router(s)
    run(router, ChannelMessage("OOC", Actor("Eve", None), SpeechKind.SAY, "cricket !pose"))
    assert s.registry.dispatched == []          # unauthorized -> not a command


# -- RP pose name-doubling: emit when the model already names the bot -----------
def test_rp_pose_with_leading_name_uses_emit():
    s = make_services()
    router = Router(s)
    resp = Response(text="Cricket's dome swivels with a whistle.", action="pose")
    router._dispatch_response(resp, None, "room", "x")
    assert ("emit_room", "Cricket's dome swivels with a whistle.") in s.actions.calls
    assert not any(c[0] == "pose_room" for c in s.actions.calls)


def test_rp_pose_without_name_uses_pose():
    s = make_services()
    router = Router(s)
    resp = Response(text="*beeps angrily and rolls back*", action="pose")
    router._dispatch_response(resp, None, "room", "x")
    assert ("pose_room", "*beeps angrily and rolls back*") in s.actions.calls
    assert not any(c[0] == "emit_room" for c in s.actions.calls)


def test_emit_helper_always_raw_emit_for_poses():
    # SW1 convention: a pose is a raw @emit (never @pose, which would prepend "Cricket").
    from cricket.commands.builtins import _emit
    from cricket.persona.base import Response

    calls = []
    actions = SimpleNamespace(
        pose_room=lambda t: calls.append(("pose_room", t)),
        emit_room=lambda t: calls.append(("emit_room", t)),
    )
    bot = SimpleNamespace(actions=actions, bot_identity=BotIdentity(name="Cricket"))
    _emit(bot, "Room1", "pose", Response("Cricket's dome swivels.", action="pose"))
    _emit(bot, "Room1", "pose", Response("*beeps*", action="pose"))
    assert calls == [("emit_room", "Cricket's dome swivels."), ("emit_room", "*beeps*")]
    assert not any(k == "pose_room" for k, _ in calls)
