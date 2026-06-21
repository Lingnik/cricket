"""Route parsed events to the command registry, the persona, or the RP scene queue.

The router reads the originating location's config and applies the engagement policy:
control locations dispatch commands; chat locations consult engagement (always, or
addressed-by-prefix) before building a Turn for the persona; room traffic accumulates in
the per-room scene queue for a later manual RP trigger.

It depends on a `services` object (the daemon, or a stand-in in tests) exposing:
locations, persona, actions, registry, auth, bot_identity, memory, store, and the mutable
state muted, rp_enabled, scene_queues, recent, current_room.
"""

from __future__ import annotations

from typing import Union

from .auth import Level
from .commands.registry import CommandContext
from .mush.events import (
    ChannelMessage,
    CommandEcho,
    ConnectNotice,
    Page,
    RoomMessage,
    Unknown,
)
from .persona.base import ContextLine, Turn

RECENT_CAP = 20


class Router:
    def __init__(self, services) -> None:
        self.s = services

    async def handle(self, event) -> None:
        if isinstance(event, ChannelMessage):
            await self._handle_channel(event)
        elif isinstance(event, RoomMessage):
            self._handle_room(event.speaker.name, event.speaker.dbref, event.kind.value, event.text)
        elif isinstance(event, Unknown):
            # Unprefixed poses/emits land here; still feed the scene queue.
            self._handle_room("", None, "emit", event.raw)
        elif isinstance(event, Page):
            await self._handle_page(event)
        elif isinstance(event, (ConnectNotice, CommandEcho)):
            return

    # -- channels --------------------------------------------------------------
    async def _handle_channel(self, event: ChannelMessage) -> None:
        s = self.s
        cfg = getattr(s, "locations", {}).get(event.channel)
        self._log(event.channel, event.speaker.dbref, event.kind.value, event.text)
        if cfg is None or not cfg.enabled:
            return

        if cfg.mode == "control":
            await self._dispatch_command(
                text=event.text,
                speaker=event.speaker,
                reply=lambda t: s.actions.say_channel(event.channel, t),
            )
            return

        if cfg.mode != "chat":
            return

        if getattr(s, "muted", False):
            return

        addressed_text = self._engaged_text(cfg, event.text)
        if addressed_text is None:
            self._remember_recent(event.channel, event)
            return

        turn = Turn(
            mode="chat",
            location=event.channel,
            location_kind="channel",
            directives=cfg.directives,
            speaker=event.speaker.name,
            speaker_dbref=event.speaker.dbref or "",
            text=addressed_text,
            context=list(getattr(s, "recent", {}).get(event.channel, [])),
            bot_identity=getattr(s, "bot_identity", None),
            memory=getattr(s, "memory", None),
        )
        self._remember_recent(event.channel, event)

        resp = await s.persona.respond(turn)
        if resp is not None:
            self._dispatch_response(resp, event.channel, "channel", event.speaker.name)

    def _engaged_text(self, cfg, text: str) -> Union[str, None]:
        """Return the text to act on if engaged, else None.

        `always`: act on the whole line. `addressed`: act only when the line starts
        with a configured prefix, returning the remainder.
        """
        if cfg.engagement == "always":
            return text
        low = text.lower()
        for prefix in cfg.prefixes:
            if low.startswith(prefix.lower()):
                return text[len(prefix):].strip()
        return None

    # -- rooms -----------------------------------------------------------------
    def _handle_room(self, speaker: str, dbref, kind: str, text: str) -> None:
        s = self.s
        room = getattr(s, "current_room", None)
        if room is None:
            return
        self._log(room, dbref, kind, text)
        if not getattr(s, "rp_enabled", {}).get(room):
            return
        s.scene_queues.setdefault(room, []).append(
            ContextLine(speaker=speaker, dbref=dbref, kind=kind, text=text)
        )

    # -- pages -----------------------------------------------------------------
    async def _handle_page(self, event: Page) -> None:
        s = self.s
        level = s.auth.level_for(event.sender)
        if level < Level.ADMIN:
            return
        await self._dispatch_command(
            text=event.text,
            speaker=event.sender,
            reply=lambda t: s.actions.page(event.sender.name, t),
        )

    # -- helpers ---------------------------------------------------------------
    async def _dispatch_command(self, text: str, speaker, reply) -> None:
        s = self.s
        parts = text.split()
        if not parts:
            return
        name, args = parts[0], parts[1:]
        ctx = CommandContext(
            source="mush",
            level=s.auth.level_for(speaker),
            reply=reply,
            invoker_dbref=speaker.dbref,
            invoker_name=speaker.name,
            bot=s,
        )
        await s.registry.dispatch(name, args, ctx)

    def _dispatch_response(self, resp, location, location_kind, fallback_target) -> None:
        actions = self.s.actions
        if location_kind == "channel":
            if resp.action == "pose":
                actions.pose_channel(location, resp.text)
            elif resp.action == "page":
                actions.page(resp.target or fallback_target, resp.text)
            else:
                actions.say_channel(location, resp.text)
        else:
            if resp.action == "pose":
                actions.pose_room(resp.text)
            elif resp.action == "emit":
                actions.emit_room(resp.text)
            elif resp.action == "page":
                actions.page(resp.target or fallback_target, resp.text)
            else:
                actions.say_room(resp.text)

    def _remember_recent(self, location: str, event: ChannelMessage) -> None:
        recent = getattr(self.s, "recent", None)
        if recent is None:
            return
        buf = recent.setdefault(location, [])
        buf.append(
            ContextLine(
                speaker=event.speaker.name,
                dbref=event.speaker.dbref,
                kind=event.kind.value,
                text=event.text,
            )
        )
        if len(buf) > RECENT_CAP:
            del buf[: len(buf) - RECENT_CAP]

    def _log(self, location, actor_dbref, kind, text) -> None:
        store = getattr(self.s, "store", None)
        if store is None:
            return
        store.log_event(location, actor_dbref, kind, text)
