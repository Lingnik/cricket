"""Parse raw MUSH lines into typed events.

Formats are PennMUSH 1.8.7p0 defaults (see docs/DESIGN.md for source citations).
Patterns are overridable via the `patterns` argument so a different server or a
customized @chatformat can be accommodated without editing code.

The parser is stateful only for command-echo framing: the bot sets OUTPUTPREFIX and
OUTPUTSUFFIX to fixed sentinel strings, so any line between those sentinels is output
caused by a command the bot issued, surfaced as CommandEcho.
"""

from __future__ import annotations

import re
from typing import Union

from .events import (
    Actor,
    ChannelMessage,
    CommandEcho,
    ConnectNotice,
    MushEvent,
    Page,
    RoomMessage,
    SpeechKind,
    Unknown,
)

# Sentinel strings the bot sends via the OUTPUTPREFIX / OUTPUTSUFFIX telnet verbs.
# They must be distinctive enough never to occur in normal world traffic.
OUTPUTPREFIX_SENTINEL = "<<CRICKET-CMD-BEGIN>>"
OUTPUTSUFFIX_SENTINEL = "<<CRICKET-CMD-END>>"

# Default PennMUSH 1.8.7p0 line patterns.
DEFAULT_PATTERNS = {
    # Spoofable output carries a PARANOID/NOSPOOF prefix when the bot is set PARANOID.
    "nospoof_owned": re.compile(
        r"^\[(?P<oname>[^(]+)\(#(?P<odbref>\d+)\)'s [^(]+\(#\d+\)\] (?P<rest>.*)$"
    ),
    "nospoof_paranoid": re.compile(
        r"^\[(?P<name>[^(\]]+)\(#(?P<dbref>\d+)\)\] (?P<rest>.*)$"
    ),
    "nospoof_plain": re.compile(r"^\[(?P<name>[^:\]]+):\] (?P<rest>.*)$"),
    # Channel: "<Chan> ..." (extchat.c fmt "<%s> %s %s").
    "channel": re.compile(r"^<(?P<chan>[^>]+)> (?P<rest>.*)$"),
    # A say, used both inside a channel line and for room speech.
    "say": re.compile(r'^(?P<who>\S+) says, "(?P<text>.*)"$'),
    # Pages.
    "page": re.compile(r"^(?P<who>\S+) pages: (?P<text>.*)$"),
    "page_to": re.compile(r"^(?P<who>\S+) pages \(to [^)]*\): (?P<text>.*)$"),
    # Connect notices.
    "connect": re.compile(r"^(?P<who>\S+) has (?P<verb>connected|disconnected)\.$"),
}


class Parser:
    """Turns raw lines into MushEvents. One instance per connection (it holds the
    command-echo framing state)."""

    def __init__(self, patterns: Union[dict, None] = None) -> None:
        self._p = patterns or DEFAULT_PATTERNS
        self._in_command_echo = False

    def parse(self, line: str) -> Union[MushEvent, None]:
        """Classify one line. Returns a MushEvent, or None for a bare sentinel line."""
        if line == OUTPUTPREFIX_SENTINEL:
            self._in_command_echo = True
            return None
        if line == OUTPUTSUFFIX_SENTINEL:
            self._in_command_echo = False
            return None
        if self._in_command_echo:
            return CommandEcho(text=line)

        p = self._p

        # 1. PARANOID / NOSPOOF prefixed (spoofable) output -> attribute by bracket.
        m = p["nospoof_owned"].match(line)
        if m:
            actor = Actor(m.group("oname").strip(), "#" + m.group("odbref"))
            return self._classify_room(actor, m.group("rest"))
        m = p["nospoof_paranoid"].match(line)
        if m:
            actor = Actor(m.group("name").strip(), "#" + m.group("dbref"))
            return self._classify_room(actor, m.group("rest"))
        m = p["nospoof_plain"].match(line)
        if m:
            actor = Actor(m.group("name").strip(), None)
            return self._classify_room(actor, m.group("rest"))

        # 2. Channel line.
        m = p["channel"].match(line)
        if m:
            chan = m.group("chan")
            rest = m.group("rest")
            sm = p["say"].match(rest)
            if sm:
                return ChannelMessage(
                    chan, Actor(sm.group("who"), None), SpeechKind.SAY, sm.group("text")
                )
            # Otherwise a pose: first token is the actor, remainder is the pose text.
            # Note: comtitles can prepend tokens and break this; acceptable for v1.
            who, _, text = rest.partition(" ")
            return ChannelMessage(chan, Actor(who, None), SpeechKind.POSE, text)

        # 3. Pages.
        m = p["page_to"].match(line)
        if m:
            return Page(Actor(m.group("who"), None), m.group("text"))
        m = p["page"].match(line)
        if m:
            return Page(Actor(m.group("who"), None), m.group("text"))

        # 4. Connect notices.
        m = p["connect"].match(line)
        if m:
            return ConnectNotice(
                Actor(m.group("who"), None), m.group("verb") == "connected"
            )

        # 5. Room say (no prefix).
        m = p["say"].match(line)
        if m:
            return RoomMessage(
                Actor(m.group("who"), None), SpeechKind.SAY, m.group("text")
            )

        # 6. Fallback.
        return Unknown(raw=line)

    def _classify_room(self, actor: Actor, rest: str):
        """Reclassify the de-prefixed remainder of a PARANOID/NOSPOOF line, keeping the
        bracket actor (the trustworthy source).

        With PARANOID the server prepends the bracket to room says, poses, and emits AND
        to connect notices -- e.g. `[Bob(#5)] Bob has connected.`, `[Bob(#5)] Bob waves.`,
        `[Bob(#5)] Bob says, "hi"`, `[Bob(#5)] A cold wind blows.` So all of those must be
        recognized here, not just say-vs-emit. A pose is detected by the remainder leading
        with the actor's own name."""
        p = self._p
        cm = p["connect"].match(rest)
        if cm:
            return ConnectNotice(actor, cm.group("verb") == "connected")
        sm = p["say"].match(rest)
        if sm:
            return RoomMessage(actor, SpeechKind.SAY, sm.group("text"))
        if actor.name and rest.startswith(actor.name + " "):
            return RoomMessage(actor, SpeechKind.POSE, rest[len(actor.name) + 1 :])
        return RoomMessage(actor, SpeechKind.EMIT, rest)
