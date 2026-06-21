"""The daemon: wires the connection, parser, router, registry, actions, memory, persona,
the control socket, and the HTTP control panel into one asyncio process, and holds the
shared mutable state that commands, the router, and the HTTP panel all touch.

The daemon instance IS the `services` object passed to the router and to command
contexts. It exposes config, persona, actions, registry, auth, bot_identity, locations,
memory, store, config_store, and the mutable state muted / rp_enabled / scene_queues /
recent / current_room.

Behavioral configuration (identity, locations, directives, prompts, inference) comes from
the *active persona profile* in the config DB, not from the TOML. The HTTP panel edits
profiles; loop-side coroutines (set_muted, set_rp, reload_active_profile) are the single
writer of loop-owned state, marshaled from the HTTP thread.
"""

from __future__ import annotations

import asyncio

from .auth import Allowlist, Level
from .commands.builtins import register_builtins
from .commands.registry import Registry
from .config import Config
from .control import ControlServer
from .http_api import HttpConfigServer
from .memory.store import MemoryHandle, MemoryStore
from .mush.actions import Actions
from .mush.connection import Connection
from .mush.events import CommandEcho
from .mush.protocol import Parser
from .persona.base import BotIdentity
from .persona.stub import StubPersona
from .profiles import DEFAULT_PROFILE, ConfigStore, derive_runtime
from .router import Router


class Bot:
    def __init__(self, config: Config, persona=None) -> None:
        self.config = config

        # Persistent stores: config DB (committed) and memory DB (gitignored).
        self.config_store = ConfigStore(config.paths.config_db)
        self.config_store.seed_default_if_empty(DEFAULT_PROFILE)
        self.store = MemoryStore(config.paths.memory_db)
        self.memory = MemoryHandle(self.store)

        # Mutable runtime state shared by router + commands + HTTP panel.
        self.muted = False
        self.rp_enabled: dict = {}
        self.scene_queues: dict = {}
        self.recent: dict = {}
        self.current_room = None

        # Behavioral config from the active profile: bot_identity, locations, auth, actions.
        self.active_profile = None
        self.active_profile_doc = None  # full active profile doc; LlmPersona reads it
        self.bot_identity = BotIdentity(name=config.mush.name or "cricket")
        self.locations: dict = {}
        self.auth = Allowlist()
        self.actions = Actions(self._send_raw)
        self._apply_active_profile()

        # Persona seam (stub by default; phase 2 swaps in LlmPersona).
        self.persona = persona or StubPersona()

        # Command layer.
        self.registry = Registry()
        register_builtins(self.registry)

        # Event pipeline.
        self.parser = Parser()
        self.router = Router(self)

        # Connection, control socket, and HTTP panel are built in run().
        self.connection = None
        self.control = ControlServer(self, port=config.control.port)
        self.http = None

    # -- profile application ---------------------------------------------------
    def _build_allowlist(self, location_admins: dict) -> Allowlist:
        allow = Allowlist()
        for dbref in self.config.auth.operators:
            allow.grant(dbref, Level.OPERATOR)
        for dbref in self.config.auth.wizards:
            allow.grant(dbref, Level.WIZARD)
        for dbref in self.config.auth.admins:
            allow.grant(dbref, Level.ADMIN)
        for admins in location_admins.values():
            for dbref in admins:
                allow.grant(dbref, Level.ADMIN)
        return allow

    def _build_actions(self) -> None:
        rate_limits = {
            name: loc.rate_limit
            for name, loc in self.locations.items()
            if loc.rate_limit
        }
        self.actions = Actions(self._send_raw, rate_limits=rate_limits)

    def _apply_active_profile(self) -> None:
        """Re-derive bot_identity, locations, auth, and actions from the active profile."""
        active = self.config_store.active()
        if active is None:
            self.active_profile = None
            self.active_profile_doc = None
            self.locations = {}
            self.auth = self._build_allowlist({})
            self._build_actions()
            return
        name, doc = active
        rt = derive_runtime(doc)
        self.active_profile = name
        self.active_profile_doc = doc
        self.bot_identity = rt.bot_identity
        if not self.bot_identity.name:
            self.bot_identity = BotIdentity(name=self.config.mush.name or "cricket")
        self.locations = rt.locations
        self.auth = self._build_allowlist(rt.location_admins)
        self._build_actions()

    # -- loop-side coroutines (single writer of loop-owned state) --------------
    async def reload_active_profile(self) -> dict:
        self._apply_active_profile()
        return self.status_snapshot()

    async def set_muted(self, muted: bool) -> dict:
        self.muted = bool(muted)
        return self.status_snapshot()

    async def set_rp(self, room: str, enabled: bool) -> dict:
        self.rp_enabled[room] = bool(enabled)
        self.scene_queues.setdefault(room, [])
        return self.status_snapshot()

    def status_snapshot(self) -> dict:
        """A plain, copy-only snapshot safe to read from another thread."""
        connected = self.connection is not None and getattr(
            self.connection, "connected", False
        )
        return {
            "connected": bool(connected),
            "muted": self.muted,
            "active_profile": self.active_profile,
            "rp_enabled": [room for room, on in self.rp_enabled.items() if on],
            "scene_queue_sizes": {r: len(q) for r, q in self.scene_queues.items()},
            "current_room": self.current_room,
            "location_count": len(self.locations),
        }

    # -- io --------------------------------------------------------------------
    def _send_raw(self, line: str) -> None:
        if self.connection is not None:
            self.connection.send(line)

    def _on_line(self, line: str) -> None:
        event = self.parser.parse(line)
        if event is None:
            return
        if isinstance(event, CommandEcho):
            # Output framed by OUTPUTPREFIX/SUFFIX = response to a command we issued.
            self._handle_command_echo(event.text)
            return
        # Fire-and-forget so a slow persona never blocks the read loop.
        asyncio.ensure_future(self.router.handle(event))

    def _handle_command_echo(self, text: str) -> None:
        # The room-probe from _setup_commands reports the bot's current location so the
        # RP scene queue and !pose have a room to key on.
        if text.startswith("CRICKET_ROOM="):
            parts = text.split("=", 2)
            if len(parts) >= 2 and parts[1].strip():
                self.current_room = parts[1].strip()
        # Admin dbref->name resolution, so control-channel auth (which sees only a name)
        # works immediately on connect -- not only after that admin has produced
        # PARANOID room output. Format: "CRICKET_RESOLVE=#4=Bazil".
        elif text.startswith("CRICKET_RESOLVE="):
            parts = text.split("=", 2)
            if len(parts) == 3 and parts[1].strip() and parts[2].strip():
                self.store.upsert_actor(parts[1].strip(), parts[2].strip())

    def _setup_commands(self) -> list:
        """Commands to run on each (re)connect: ensure NOSPOOF/PARANOID, join every
        chat/control channel via @channel/on (addcom is disabled on this server), probe
        our current room (scene-queue key), and resolve each location admin's dbref to a
        name so control-channel auth works before they have posted anything."""
        cmds = ["@set me=NOSPOOF", "@set me=PARANOID"]
        admins = set()
        for name, loc in self.locations.items():
            if loc.mode in ("chat", "control"):
                cmds.append("@channel/on %s" % name)
            for a in getattr(loc, "admins", []) or []:
                if a.startswith("#"):
                    admins.add(a)
        cmds.append("think CRICKET_ROOM=[loc(me)]=[name(loc(me))]")
        for dbref in sorted(admins):
            cmds.append("think CRICKET_RESOLVE=%s=[name(%s)]" % (dbref, dbref))
        return cmds

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        self.connection = Connection(
            host=self.config.mush.host,
            port=self.config.mush.port,
            name=self.config.mush.name,
            password=self.config.mush.password,
            on_line=self._on_line,
            use_tls=self.config.mush.use_tls,
            setup_commands=self._setup_commands(),
        )
        await self.control.start()
        self.http = HttpConfigServer(
            self, self.config.http.host, self.config.http.port, loop
        )
        self.http.start()
        try:
            await asyncio.gather(
                self.connection.run(),
                self.control.serve_forever(),
            )
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self.connection is not None:
            self.connection.close()
        self.control.close()
        if self.http is not None:
            self.http.stop()
        self.store.close()
        self.config_store.close()


def build_bot(config: Config, persona: str = "stub") -> Bot:
    """Construct a Bot with the chosen persona. `llm` wires LlmPersona to a local Ollama
    client, reading the active profile's prompts/inference live; `stub` is the no-model
    default used by tests and offline runs."""
    bot = Bot(config)
    if persona == "llm":
        from .lore.loader import LoreStore
        from .lore.vector import VectorIndex
        from .lore.wiki import WikiIndex
        from .persona.inference import OllamaInferenceClient
        from .persona.llm import LlmPersona

        inference = (bot.active_profile_doc or {}).get("inference", {})
        client = OllamaInferenceClient(model=inference.get("model"))
        lore = LoreStore("lore")
        wiki = WikiIndex("wiki-cache")
        vector = VectorIndex("wiki-cache")  # Tier-2 semantic fallback (empty if not built)
        bot.persona = LlmPersona(
            client, lambda: bot.active_profile_doc, lore=lore, wiki=wiki, vector=vector
        )
    return bot


async def run_async(config: Config, persona: str = "stub") -> None:
    await build_bot(config, persona).run()
