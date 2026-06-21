import asyncio
from types import SimpleNamespace

from cricket.auth import Allowlist, Level
from cricket.config import LocationConfig
from cricket.mush.events import ChannelMessage, RoomMessage, SpeechKind, Unknown
from cricket.mush.events import Actor
from cricket.persona.base import BotIdentity, Response
from cricket.router import Router, SCENE_QUEUE_CAP


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
    assert ("pose_room", "*beeps furiously at the meatbags*") in actions.calls
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


def test_scene_queue_capped_drops_oldest():
    s = make_services()
    s.rp_enabled = {"Room1": True}
    router = Router(s)
    total = SCENE_QUEUE_CAP + 25
    for i in range(total):
        run(router, RoomMessage(Actor("Bob", "#9"), SpeechKind.SAY, "line %d" % i))
    q = s.scene_queues["Room1"]
    assert len(q) == SCENE_QUEUE_CAP  # bounded
    # oldest dropped, newest kept, order preserved
    assert q[0].text == "line %d" % (total - SCENE_QUEUE_CAP)
    assert q[-1].text == "line %d" % (total - 1)


def test_scene_queue_under_cap_unchanged():
    s = make_services()
    s.rp_enabled = {"Room1": True}
    router = Router(s)
    for i in range(5):
        run(router, RoomMessage(Actor("Bob", "#9"), SpeechKind.SAY, "line %d" % i))
    q = s.scene_queues["Room1"]
    assert len(q) == 5
    assert q[0].text == "line 0"


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


def test_emit_helper_uses_emit_when_pose_names_the_bot():
    # The RP !pose path (builtins._emit) must also avoid name-doubling.
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
    assert ("emit_room", "Cricket's dome swivels.") in calls
    assert ("pose_room", "*beeps*") in calls
