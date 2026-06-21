"""The frozen contract between the program (phase 1) and the persona (phase 2).

The daemon builds a Turn and calls Persona.respond; a Response (or None to stay silent)
comes back. The daemon owns MUSH formatting, rate limiting, and logging -- the persona
returns plain text and an action. See docs/PERSONA_AFFORDANCES.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Union, runtime_checkable


@dataclass(frozen=True)
class BotIdentity:
    """How the bot presents itself in the world."""

    name: str
    dbref: Union[str, None] = None
    pronouns: str = "they/them"


@dataclass(frozen=True)
class ContextLine:
    """One prior line of context (recent chat, or a line in the RP scene queue)."""

    speaker: str
    dbref: Union[str, None]
    kind: str  # "say" | "pose" | "emit"
    text: str


@dataclass
class Turn:
    """Everything the persona needs to decide a single response.

    For an RP `!pose` trigger, `context` is the room's accumulated scene queue and
    `text` is empty -- compose a pose from the scene, not a reply to one line.
    """

    mode: str  # "chat" | "rp"
    location: str
    location_kind: str  # "channel" | "room"
    directives: str
    speaker: str
    speaker_dbref: str
    text: str
    context: list = field(default_factory=list)  # list[ContextLine], oldest -> newest
    bot_identity: Union[BotIdentity, None] = None
    memory: Any = None  # MemoryHandle (see cricket.memory.store)


@dataclass(frozen=True)
class Response:
    """What the persona wants to do. `text` is plain; the daemon decorates it."""

    text: str
    action: str = "say"  # "say" | "pose" | "emit" | "page"
    target: Union[str, None] = None  # for page; defaults to the turn's location


@runtime_checkable
class Persona(Protocol):
    """The single method the daemon depends on."""

    async def respond(self, turn: Turn) -> Union[Response, None]: ...
