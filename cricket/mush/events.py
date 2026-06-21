"""Typed events the parser produces from raw MUSH lines.

All events are immutable. An Actor carries a stable dbref when the server gave us
one (via the PARANOID prefix); dbref is None when only a display name was visible.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Union


class SpeechKind(enum.Enum):
    """How a line of speech was produced in the world."""

    SAY = "say"
    POSE = "pose"
    EMIT = "emit"


@dataclass(frozen=True)
class Actor:
    """Who produced a line. dbref is the stable id, e.g. "#1234", when known."""

    name: str
    dbref: Union[str, None] = None


@dataclass(frozen=True)
class ChannelMessage:
    """A line spoken on a comsys channel, e.g. `<Public> Bob says, "hi"`."""

    channel: str
    speaker: Actor
    kind: SpeechKind
    text: str


@dataclass(frozen=True)
class Page:
    """A private page, e.g. `Bob pages: hi there`."""

    sender: Actor
    text: str


@dataclass(frozen=True)
class RoomMessage:
    """A say/pose/emit in the room the bot occupies."""

    speaker: Actor
    kind: SpeechKind
    text: str


@dataclass(frozen=True)
class ConnectNotice:
    """A `X has connected.` / `X has disconnected.` notice."""

    actor: Actor
    connected: bool


@dataclass(frozen=True)
class CommandEcho:
    """A line that is part of the output of a command the bot itself issued.

    The connection brackets such output with OUTPUTPREFIX/OUTPUTSUFFIX sentinels so
    it is never mistaken for spontaneous world traffic.
    """

    text: str


@dataclass(frozen=True)
class Unknown:
    """A line the parser did not classify. Kept verbatim.

    Poses and emits without a PARANOID prefix land here; the RP scene queue still
    captures them, so they reach roleplay context.
    """

    raw: str


MushEvent = Union[
    ChannelMessage,
    Page,
    RoomMessage,
    ConnectNotice,
    CommandEcho,
    Unknown,
]
