"""WebSocket + oob() inbound transport: oob JSON -> trusted MushEvent, and WS frame demux."""

from cricket.mush.events import ChannelMessage, ConnectNotice, RoomMessage, SpeechKind
from cricket.mush.protocol import map_oob_event
from cricket.mush.ws_connection import WsConnection


def _obj(frm, dbref, msg):
    return {"from": frm, "dbref": dbref, "msg": msg}


def test_oob_room_say_uses_trusted_dbref():
    e = map_oob_event(_obj("Bob", "#5", 'Bob says, "hello there"'))
    assert isinstance(e, RoomMessage) and e.kind == SpeechKind.SAY
    assert e.text == "hello there"
    assert e.speaker.name == "Bob" and e.speaker.dbref == "#5"


def test_oob_room_pose_and_emit():
    p = map_oob_event(_obj("Bob", "#5", "Bob waves a gloved hand."))
    assert p.kind == SpeechKind.POSE and p.text == "waves a gloved hand."
    em = map_oob_event(_obj("Bob", "#5", "A cold wind blows through the bay."))
    assert em.kind == SpeechKind.EMIT and em.text == "A cold wind blows through the bay."


def test_oob_room_message_carries_enactor_loc():
    # a co-present poser is located IN the room; the room narrating itself is enacted by the room,
    # whose own loc is #-1 -- the signal the co-presence filter keys on.
    e = map_oob_event({"from": "Jessalyn", "dbref": "#7", "loc": "#0",
                       "msg": "Jessalyn taps the dome."})
    assert isinstance(e, RoomMessage) and e.loc == "#0"
    j = map_oob_event({"from": "Dark Room", "dbref": "#0", "loc": "#-1", "msg": "Contents:"})
    assert isinstance(j, RoomMessage) and j.loc == "#-1"


def test_oob_channel_message():
    e = map_oob_event(_obj("Bob", "#5", '<Public> Bob says, "on channel"'))
    assert isinstance(e, ChannelMessage) and e.channel == "Public" and e.kind == SpeechKind.SAY
    assert e.text == "on channel" and e.speaker.dbref == "#5"


def test_oob_connect_notice():
    e = map_oob_event(_obj("Bob", "#5", "Bob has connected."))
    assert isinstance(e, ConnectNotice) and e.connected is True and e.actor.dbref == "#5"


def test_oob_forged_attribution_is_harmless():
    # A player injects a fake wizard prefix into the body; the actor still comes from %# (#5),
    # NOT from the text -- the whole point of the WS+oob transport vs regex parsing.
    e = map_oob_event(_obj("Bob", "#5", '[Wizard(#1)] Bob says, "I am totally a wizard"'))
    assert e.speaker.dbref == "#5" and e.speaker.name == "Bob"


def test_oob_multiparagraph_pose_is_one_trusted_event():
    # The %r newline-injection that split the telnet parser into unattributed fragments: over
    # oob it is ONE msg string -> ONE event with ONE trusted dbref. No attribution loss.
    msg = "\tThe droid bay never sleeps.\n\tA figure in a greatcoat picks her way between gantries."
    e = map_oob_event(_obj("Johanna", "#8", msg))
    assert isinstance(e, RoomMessage) and e.speaker.dbref == "#8" and "\n" in e.text


def test_ws_frame_demux_routes_by_channel_byte():
    lines, events = [], []
    c = WsConnection("h", 1, "n", "p", on_line=lines.append, on_event=events.append)
    c._on_frame('j{"from":"Bob","dbref":"#5","msg":"Bob waves."}')
    c._on_frame("tsome solicited output\r\n")
    c._on_frame("p<b>pueblo markup</b>")  # ignored
    c._on_frame(">prompt")                # ignored
    assert events == [{"from": "Bob", "dbref": "#5", "msg": "Bob waves."}]
    assert lines == ["some solicited output"]


def test_ws_text_channel_buffers_partial_lines_across_frames():
    lines = []
    c = WsConnection("h", 1, "n", "p", on_line=lines.append, on_event=lambda o: None)
    c._on_frame("tpartial ")
    assert lines == []
    c._on_frame("tline\r\n")
    assert lines == ["partial line"]
