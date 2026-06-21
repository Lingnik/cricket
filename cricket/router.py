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

import re
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
# Max lines kept in a room's RP scene queue. Beyond this the oldest are dropped so a
# long scene cannot grow unbounded and blow the model's context window.
SCENE_QUEUE_CAP = 60

# Connection/disconnection and channel join/leave announcements. For now these are noise:
# we ignore them entirely (no context, no reply). (Later Cricket may harass people on
# connect / mock reconnects -- that would re-enable these as a deliberate trigger.)
_CHANNEL_NOTICE = re.compile(
    r"^has ((?:re)?connected|disconnected|joined this channel|left this channel)\b",
    re.IGNORECASE,
)


def _same_poser(line, speaker, dbref) -> bool:
    """True if a new room line continues the previous poser's block: same dbref when both
    have one, else the same (non-empty) speaker name."""
    ld = getattr(line, "dbref", None)
    if dbref and ld:
        return ld == dbref
    sp = (speaker or "").strip().lower()
    return bool(sp) and (line.speaker or "").strip().lower() == sp


class Router:
    def __init__(self, services) -> None:
        self.s = services

    def _is_self(self, actor) -> bool:
        """True if `actor` is the bot itself. The bot sees its own channel/room output
        echoed back; without this it would react to its own messages in a loop."""
        bid = getattr(self.s, "bot_identity", None)
        if bid is None or actor is None:
            return False
        if actor.dbref and bid.dbref and actor.dbref == bid.dbref:
            return True
        if actor.name and bid.name and actor.name.lower() == bid.name.lower():
            return True
        return False

    async def handle(self, event) -> None:
        actor = (
            getattr(event, "speaker", None)
            or getattr(event, "sender", None)
            or getattr(event, "actor", None)
        )
        if self._is_self(actor):
            return
        if isinstance(event, ChannelMessage):
            await self._handle_channel(event)
        elif isinstance(event, RoomMessage):
            self._handle_room(event.speaker.name, event.speaker.dbref, event.kind.value, event.text)
        elif isinstance(event, Unknown):
            # Unprefixed poses/emits land here; still feed the scene queue.
            self._handle_room("", None, "emit", event.raw)
        elif isinstance(event, Page):
            await self._handle_page(event)
        elif isinstance(event, ConnectNotice):
            await self._handle_connect(event)
        elif isinstance(event, CommandEcho):
            return

    async def _handle_connect(self, event) -> None:
        """Harass-on-connect: when enabled, page the newcomer an unprompted, personalized
        insult. It is a chat turn keyed on the connector, so retrieval pulls THEIR dossier
        (OOC roast facet) -- the abuse is informed by what Cricket knows about them."""
        if not getattr(event, "connected", False):
            return  # connects only, not disconnects
        s = self.s
        if getattr(s, "muted", False) or not getattr(s, "harass_on_connect", False):
            return
        persona = getattr(s, "persona", None)
        name = (getattr(event.actor, "name", "") or "").strip()
        if persona is None or not name:
            return
        turn = Turn(
            mode="chat",
            location="(connect)",
            location_kind="channel",
            directives=(
                "%s just logged into the game. UNPROMPTED, greet them with a hostile, "
                "personalized jab -- one or two lines, in character, using what you know "
                "about them." % name
            ),
            speaker=name,
            speaker_dbref=getattr(event.actor, "dbref", None),
            text="(just connected)",
            context=[],
            bot_identity=getattr(s, "bot_identity", None),
            memory=getattr(s, "memory", None),
        )
        resp = await persona.respond(turn)
        if resp is not None and resp.text.strip():
            s.actions.page(name, resp.text)

    # -- channels --------------------------------------------------------------
    async def _handle_channel(self, event: ChannelMessage) -> None:
        if _CHANNEL_NOTICE.match((event.text or "").strip()):
            return  # connect/disconnect/join/leave -- noise; ignore entirely for now
        s = self.s
        cfg = getattr(s, "locations", {}).get(event.channel)
        self._log(event.channel, event.speaker.dbref, event.kind.value, event.text)
        if cfg is None or not cfg.enabled:
            return

        if cfg.mode == "control":
            cmdline = self._addressed_command(event.text)
            if not cmdline:
                return  # not addressed to the bot (or bare name) -> ignore silently
            if cmdline.split()[0].lower() in ("!help", "help"):
                await self._handle_help(event.speaker)
                return
            level = self._control_level(cfg, event.speaker)
            if level is None:
                return  # speaker is not an authorized admin -> ignore silently
            await self._dispatch_command(
                cmdline,
                event.speaker,
                lambda t: s.actions.say_channel(event.channel, t),
                level,
            )
            return

        if cfg.mode != "chat":
            return

        # A chat channel can also be where admins drive RP: an addressed bang-command
        # ("Cricket !pose") from an authorized admin is dispatched as a command. Bare
        # addressed chat ("Cricket, hi") and non-admin senders fall through to chat.
        cmdline = self._addressed_command(event.text)
        if cmdline and cmdline.split()[0].lower() in ("!help", "help"):
            await self._handle_help(event.speaker)
            return
        if cmdline and cmdline.startswith("!"):
            level = self._control_level(cfg, event.speaker)
            if level is not None:
                await self._dispatch_command(
                    cmdline,
                    event.speaker,
                    lambda t: s.actions.say_channel(event.channel, t),
                    level,
                )
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
            self._remember_own(event.channel, resp.text)

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

    def _addressed_command(self, text: str) -> Union[str, None]:
        """For a control channel, return the command line iff the message is addressed
        to the bot by name (e.g. "Cricket !pose" -> "!pose"); else None.

        The bot must be named explicitly so it ignores channel chatter and system
        notices ("Bob has joined this channel") instead of parsing them as commands.
        """
        bid = getattr(self.s, "bot_identity", None)
        name = (bid.name if bid is not None else "") or ""
        t = (text or "").strip()
        if not name or not t:
            return None
        if not t.lower().startswith(name.lower()):
            return None
        rest = t[len(name):]
        if rest and rest[0] not in " ,:":
            return None  # e.g. "Cricketish" is not addressing "Cricket"
        return rest.lstrip(" ,:").strip()

    def _control_level(self, cfg, speaker):
        """Authorize a control-channel command. Channels carry only a NAME (no dbref),
        so in addition to the global dbref allowlist we match the speaker's name against
        the location's admins -- accepting bare-name entries and resolving admin dbrefs
        to names via the actors table (populated from PARANOID room output). Returns the
        granted Level, or None if the speaker is not an authorized admin.

        Name-based auth is weaker than dbref auth; it is acceptable here because channel
        speech is server-attributed and hard to spoof. Sensitive commands should still
        prefer pages (which can carry a dbref) where possible.
        """
        s = self.s
        glvl = s.auth.level_for(speaker)
        admins = list(getattr(cfg, "admins", []) or [])
        dbref_admins = {a for a in admins if a.startswith("#")}
        name_admins = {a.lower() for a in admins if not a.startswith("#")}
        store = getattr(s, "store", None)
        if store is not None:
            for d in dbref_admins:
                rec = store.actor(d)
                if rec and rec.get("name"):
                    name_admins.add(rec["name"].lower())
        authorized = glvl >= Level.ADMIN
        if speaker.dbref and speaker.dbref in dbref_admins:
            authorized = True
        if speaker.name and speaker.name.lower() in name_admins:
            authorized = True
        if not authorized:
            return None
        return glvl if glvl >= Level.ADMIN else Level.ADMIN

    def _admin_names(self) -> set:
        """Lowercased names of all configured admins -- bare-name entries plus dbref
        entries resolved to a name via the actors table."""
        s = self.s
        names = set()
        store = getattr(s, "store", None)
        for loc in getattr(s, "locations", {}).values():
            for a in getattr(loc, "admins", []) or []:
                if a.startswith("#"):
                    rec = store.actor(a) if store is not None else None
                    if rec and rec.get("name"):
                        names.add(rec["name"].lower())
                else:
                    names.add(a.lower())
        return names

    def _invoker_level(self, actor) -> Level:
        """Auth level for a command invoker, resolving name-only actors (e.g. page
        senders, who carry no dbref) against the allowlist and the configured admins.
        Defaults to PUBLIC."""
        lvl = self.s.auth.level_for(actor)
        if lvl >= Level.ADMIN:
            return lvl
        if actor.name and actor.name.lower() in self._admin_names():
            return Level.ADMIN
        return lvl

    async def _handle_help(self, actor) -> None:
        """Dispatch !help for ANY user (help is universal): pages them a command list
        scoped to their resolved role."""
        level = self._invoker_level(actor)
        await self._dispatch_command(
            "!help", actor, lambda t: self.s.actions.page(actor.name, t), level
        )

    # -- rooms -----------------------------------------------------------------
    def _handle_room(self, speaker: str, dbref, kind: str, text: str) -> None:
        s = self.s
        # Record name<->dbref from PARANOID room output so control channels (name-only)
        # can later be authorized by name.
        store = getattr(s, "store", None)
        if store is not None and dbref and speaker:
            upsert = getattr(store, "upsert_actor", None)
            if upsert is not None:
                upsert(dbref, speaker)
        room = getattr(s, "current_room", None)
        if room is None:
            return
        self._log(room, dbref, kind, text)
        if not getattr(s, "rp_enabled", {}).get(room):
            return
        queue = s.scene_queues.setdefault(room, [])
        # Block grouping: a multiline pose arrives as several socket lines; merge consecutive
        # lines from the SAME poser (by dbref, else speaker name) into one block, so each queue
        # entry is one whole pose. A change of poser closes the previous block.
        if queue and _same_poser(queue[-1], speaker, dbref):
            prev = queue[-1]
            queue[-1] = ContextLine(
                speaker=prev.speaker, dbref=prev.dbref, kind=prev.kind,
                text=(prev.text + "\n" + text).strip(),
            )
        else:
            queue.append(ContextLine(speaker=speaker, dbref=dbref, kind=kind, text=text))
        if len(queue) > SCENE_QUEUE_CAP:
            # TODO(RP-2): replace this line cap with a byte-budgeted tail + append-only ledger
            # (docs/RP-DESIGN.md). For now keep a generous cap so blocks are not dropped early.
            del queue[: len(queue) - SCENE_QUEUE_CAP]

    # -- pages -----------------------------------------------------------------
    async def _handle_page(self, event: Page) -> None:
        s = self.s
        # !help is universal: any user can page it and get a role-scoped command list.
        if "!help" in (event.text or "").lower():
            await self._handle_help(event.sender)
            return
        level = s.auth.level_for(event.sender)
        if level < Level.ADMIN:
            return
        await self._dispatch_command(
            event.text,
            event.sender,
            lambda t: s.actions.page(event.sender.name, t),
            level,
        )

    # -- helpers ---------------------------------------------------------------
    async def _dispatch_command(self, text: str, speaker, reply, level) -> None:
        s = self.s
        parts = text.split()
        if not parts:
            return
        name, args = parts[0], parts[1:]
        ctx = CommandContext(
            source="mush",
            level=level,
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
                # The model writes full third-person prose that often begins with the
                # bot's own name ("Cricket's dome swivels..."). A `pose` (`:`) prepends
                # the name too, producing "Cricket Cricket's dome...". When the text
                # already names the bot, emit it raw so the name isn't doubled.
                bid = getattr(self.s, "bot_identity", None)
                name = (bid.name if bid is not None else "") or ""
                if name and resp.text.lstrip().lower().startswith(name.lower()):
                    actions.emit_room(resp.text)
                else:
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

    def _remember_own(self, location: str, text: str) -> None:
        """Append the bot's OWN reply to a channel's history. The bot's echoed output is
        self-filtered, so without this the model never sees its own side of the
        conversation and re-treads topics it already covered."""
        recent = getattr(self.s, "recent", None)
        if recent is None:
            return
        bid = getattr(self.s, "bot_identity", None)
        name = (bid.name if bid is not None else "") or "Cricket"
        buf = recent.setdefault(location, [])
        buf.append(
            ContextLine(
                speaker=name,
                dbref=getattr(bid, "dbref", None),
                kind="say",
                text=text,
            )
        )
        if len(buf) > RECENT_CAP:
            del buf[: len(buf) - RECENT_CAP]

    def _log(self, location, actor_dbref, kind, text) -> None:
        store = getattr(self.s, "store", None)
        if store is None:
            return
        store.log_event(location, actor_dbref, kind, text)
