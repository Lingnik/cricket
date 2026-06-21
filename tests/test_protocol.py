from cricket.mush.events import (
    ChannelMessage,
    CommandEcho,
    ConnectNotice,
    Page,
    RoomMessage,
    SpeechKind,
    Unknown,
)
from cricket.mush.protocol import (
    OUTPUTPREFIX_SENTINEL,
    OUTPUTSUFFIX_SENTINEL,
    Parser,
)


def p():
    return Parser()


def test_paranoid_emit():
    ev = p().parse("[Bob(#123)] waves a flag.")
    assert isinstance(ev, RoomMessage)
    assert ev.speaker.name == "Bob"
    assert ev.speaker.dbref == "#123"
    assert ev.kind is SpeechKind.EMIT
    assert ev.text == "waves a flag."


def test_paranoid_say_keeps_bracket_actor():
    ev = p().parse('[Bob(#123)] Bob says, "hi"')
    assert isinstance(ev, RoomMessage)
    assert ev.speaker.dbref == "#123"
    assert ev.kind is SpeechKind.SAY
    assert ev.text == "hi"


def test_paranoid_owned_object_attributes_to_owner():
    ev = p().parse("[Alice(#5)'s Widget(#9)] beeps.")
    assert isinstance(ev, RoomMessage)
    assert ev.speaker.name == "Alice"
    assert ev.speaker.dbref == "#5"
    assert ev.kind is SpeechKind.EMIT


def test_nospoof_plain_has_no_dbref():
    ev = p().parse("[Bob:] grins.")
    assert isinstance(ev, RoomMessage)
    assert ev.speaker.name == "Bob"
    assert ev.speaker.dbref is None
    assert ev.kind is SpeechKind.EMIT
    assert ev.text == "grins."


def test_paranoid_pose_keeps_bracket_actor():
    # With PARANOID the bracket precedes the actor's own name in a pose.
    ev = p().parse("[Bob(#5)] Bob waves at everyone.")
    assert isinstance(ev, RoomMessage)
    assert ev.speaker.name == "Bob"
    assert ev.speaker.dbref == "#5"
    assert ev.kind is SpeechKind.POSE
    assert ev.text == "waves at everyone."


def test_paranoid_connect_notice_reclassified():
    ev = p().parse("[Bob(#5)] Bob has connected.")
    assert isinstance(ev, ConnectNotice)
    assert ev.actor.name == "Bob"
    assert ev.actor.dbref == "#5"
    assert ev.connected is True


def test_paranoid_disconnect_notice_reclassified():
    ev = p().parse("[Bob(#5)] Bob has disconnected.")
    assert isinstance(ev, ConnectNotice)
    assert ev.connected is False


def test_channel_say():
    ev = p().parse('<Public> Bob says, "hello there"')
    assert isinstance(ev, ChannelMessage)
    assert ev.channel == "Public"
    assert ev.speaker.name == "Bob"
    assert ev.kind is SpeechKind.SAY
    assert ev.text == "hello there"


def test_channel_pose():
    ev = p().parse("<Public> Bob waves happily")
    assert isinstance(ev, ChannelMessage)
    assert ev.channel == "Public"
    assert ev.speaker.name == "Bob"
    assert ev.kind is SpeechKind.POSE
    assert ev.text == "waves happily"


def test_page_simple():
    ev = p().parse("Bob pages: hi there")
    assert isinstance(ev, Page)
    assert ev.sender.name == "Bob"
    assert ev.text == "hi there"


def test_page_to_form():
    ev = p().parse("Bob pages (to CricketBOT): secret command")
    assert isinstance(ev, Page)
    assert ev.sender.name == "Bob"
    assert ev.text == "secret command"


def test_connect_notice():
    ev = p().parse("Bob has connected.")
    assert isinstance(ev, ConnectNotice)
    assert ev.actor.name == "Bob"
    assert ev.connected is True


def test_disconnect_notice():
    ev = p().parse("Bob has disconnected.")
    assert isinstance(ev, ConnectNotice)
    assert ev.connected is False


def test_room_say_without_prefix():
    ev = p().parse('Bob says, "hey"')
    assert isinstance(ev, RoomMessage)
    assert ev.speaker.name == "Bob"
    assert ev.speaker.dbref is None
    assert ev.kind is SpeechKind.SAY
    assert ev.text == "hey"


def test_unknown_fallback():
    ev = p().parse("The weather is fine.")
    assert isinstance(ev, Unknown)
    assert ev.raw == "The weather is fine."


def test_command_echo_framing():
    parser = p()
    assert parser.parse(OUTPUTPREFIX_SENTINEL) is None
    ev = parser.parse("You are carrying nothing.")
    assert isinstance(ev, CommandEcho)
    assert ev.text == "You are carrying nothing."
    assert parser.parse(OUTPUTSUFFIX_SENTINEL) is None
    # After the suffix, normal classification resumes.
    assert isinstance(parser.parse("The weather is fine."), Unknown)
