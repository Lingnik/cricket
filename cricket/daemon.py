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
import os

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
from .mush.protocol import Parser, map_oob_event
from .persona.base import BotIdentity
from .persona.stub import StubPersona
from .profiles import DEFAULT_PROFILE, ConfigStore, derive_runtime
from .router import Router


class Bot:
    def __init__(self, config: Config, persona=None, verbose: bool = False) -> None:
        self.config = config
        self.verbose = verbose

        # Activity bus: one publish point for messages in/out, generations, distillations -- fed
        # to live sinks (the --verbose stdout printer + the ctl tail stream).
        from .activity import ActivityBus
        self.bus = ActivityBus()

        # Persistent stores: config DB (committed) and memory DB (gitignored).
        self.config_store = ConfigStore(config.paths.config_db)
        self.config_store.seed_default_if_empty(DEFAULT_PROFILE)
        self.store = MemoryStore(config.paths.memory_db)
        self.memory = MemoryHandle(self.store)

        # Turn tracer: append-only JSONL debug log of generations + distillations. Path is
        # CRICKET_TRACE_DIR/turns-<date>.jsonl (default data/traces), so a scene's trace can be
        # isolated and analyzed after the fact. Traces are debug logs, never fed back to Cricket.
        from .trace import TurnTracer
        _trace_dir = os.environ.get("CRICKET_TRACE_DIR", "data/traces")
        _day = __import__("datetime").datetime.now().strftime("%Y%m%d")
        # Generations + distillations also fan out to the activity bus (live viewers).
        self.tracer = TurnTracer(os.path.join(_trace_dir, "turns-%s.jsonl" % _day),
                                 on_emit=self.bus.publish_event)

        # Mutable runtime state shared by router + commands + HTTP panel.
        self.muted = False
        self.harass_on_connect = False
        self.rp_enabled: dict = {}
        self.scene_queues: dict = {}
        self.scene_ledger: dict = {}  # room -> [distilled ledger lines] (append-only per scene)
        self.scene_owners: dict = {}  # room -> set of characters OTHERS control (do-not-puppet)
        self.suggestions: dict = {}   # room -> [OOC nudges {from, text, favored}] for the next pose
        self.pending_consent: dict = {}   # room -> {target} awaiting !consent-ok/!consent-deny
        self.consent_granted: dict = {}   # room -> {target} one-time grant for the next pose
        self.recent: dict = {}
        self.current_room = None
        self.current_room_desc = ""

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
        # Restart plumbing: request_restart() sets exit code 42 and trips this event; run()
        # returns the code so the CLI/supervisor can respawn the worker with fresh code.
        self._exit_code = 0
        self._restart_event = None

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
        self.harass_on_connect = bool(doc.get("harass_on_connect", False))
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

    async def set_harass(self, on: bool) -> dict:
        self.harass_on_connect = bool(on)
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
            "harass_on_connect": self.harass_on_connect,
            "active_profile": self.active_profile,
            "rp_enabled": [room for room, on in self.rp_enabled.items() if on],
            "scene_queue_sizes": {r: len(q) for r, q in self.scene_queues.items()},
            "current_room": self.current_room,
            "location_count": len(self.locations),
        }

    # -- io --------------------------------------------------------------------
    def _send_raw(self, line: str) -> None:
        if self.connection is not None:
            self.bus.publish("mush.out", line=line)
            self.connection.send(line)

    def _publish_in(self, event, raw=None) -> None:
        """Publish a heard MushEvent to the activity bus (live viewers). `raw` is the original oob
        JSON envelope on the WS transport, carried so a raw view can show the unmapped frame."""
        sp = getattr(event, "speaker", None) or getattr(event, "actor", None)
        self.bus.publish(
            "mush.in",
            speaker=getattr(sp, "name", None),
            dbref=getattr(sp, "dbref", None),
            speech=getattr(getattr(event, "kind", None), "value", None),
            channel=getattr(event, "channel", None),
            text=getattr(event, "text", None),
            raw=raw,
        )

    def _on_line(self, line: str) -> None:
        event = self.parser.parse(line)
        if event is None:
            return
        if isinstance(event, CommandEcho):
            # Output framed by OUTPUTPREFIX/SUFFIX = response to a command we issued.
            self._handle_command_echo(event.text)
            return
        # On the WS transport, heard world traffic ALSO echoes on the t channel in-band -- but the
        # trusted j channel (on_event) is authoritative. Ignore non-CommandEcho t-channel lines so
        # we don't double-handle (and don't fall back to the spoofable regex attribution).
        if self.config.mush.transport == "ws":
            return
        self._publish_in(event)
        # Fire-and-forget so a slow persona never blocks the read loop.
        asyncio.ensure_future(self.router.handle(event))

    def _on_event(self, obj: dict) -> None:
        """j-channel inbound (WebSocket): an oob() JSON envelope carrying a TRUSTED speaker
        dbref (%#). Mapped to a MushEvent without parsing attribution out of spoofable text."""
        event = map_oob_event(obj)
        if event is not None:
            self._publish_in(event, raw=obj)
            asyncio.ensure_future(self.router.handle(event))

    def _handle_command_echo(self, text: str) -> None:
        # The room-probe from _setup_commands reports the bot's current location so the
        # RP scene queue and !pose have a room to key on.
        if text.startswith("CRICKET_ROOMDESC="):
            desc = text.split("=", 1)[1].strip()
            if desc:
                self.current_room_desc = desc
        elif text.startswith("CRICKET_ROOM="):
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
        # Room description for RP setting/inspiration: strip newlines to spaces, cap length.
        cmds.append("think CRICKET_ROOMDESC=[mid(edit(describe(loc(me)),%r,%b),0,400)]")
        for dbref in sorted(admins):
            cmds.append("think CRICKET_RESOLVE=%s=[name(%s)]" % (dbref, dbref))
        # WebSocket transport: install the receiver-side relay so every heard message is mirrored
        # to the j channel as an oob() JSON object carrying the trusted enactor (%#). %-subs are
        # stored literally by &-set and evaluated when AHEAR fires (see docs/websockets.md).
        if self.config.mush.transport == "ws":
            cmds.append("@listen me=*")
            cmds.append(
                "&AHEAR me=@assert oob(name(me),Room.Emit,json(object,"
                "from,json(string,name(%#)),dbref,json(string,%#),"
                "loc,json(string,loc(%#)),ts,json(number,secs()),msg,json(string,%0)))"
            )
        return cmds

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        if self.config.mush.transport == "ws":
            from .mush.ws_connection import WsConnection
            self.connection = WsConnection(
                host=self.config.mush.host,
                port=self.config.mush.port,
                name=self.config.mush.name,
                password=self.config.mush.password,
                on_line=self._on_line,
                on_event=self._on_event,
                use_tls=self.config.mush.use_tls,
                setup_commands=self._setup_commands(),
                ws_path=self.config.mush.ws_path,
            )
        else:
            self.connection = Connection(
                host=self.config.mush.host,
                port=self.config.mush.port,
                name=self.config.mush.name,
                password=self.config.mush.password,
                on_line=self._on_line,
                use_tls=self.config.mush.use_tls,
                setup_commands=self._setup_commands(),
            )
        self._restart_event = asyncio.Event()
        # --verbose: print every activity event to stdout (your supervisor console).
        if self.verbose:
            from .activity import format_event
            self.bus.subscribe(lambda evt: print(format_event(evt), flush=True))
        # Push-only activity stream socket (the ctl tail subscribes here).
        from .stream_server import StreamServer
        _stream_port = int(os.environ.get("CRICKET_STREAM_PORT", "4252"))
        self.stream = StreamServer(self.bus, port=_stream_port)
        await self.stream.start()
        await self.control.start()
        self.http = HttpConfigServer(
            self, self.config.http.host, self.config.http.port, loop
        )
        self.http.start()
        import contextlib
        main = asyncio.gather(self.connection.run(), self.control.serve_forever())
        stop = asyncio.ensure_future(self._restart_event.wait())
        try:
            # Run until the connection/control tasks end OR a restart is requested.
            await asyncio.wait({main, stop}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            main.cancel()
            stop.cancel()
            # Await the cancelled futures so their CancelledError is retrieved (no stray warning).
            for fut in (main, stop):
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await fut
            self.shutdown()
        return self._exit_code

    def request_restart(self) -> None:
        """Ask the daemon to shut down cleanly and exit with the restart code (42). A supervising
        `cricket supervise` process respawns it with fresh code. No-op if not running."""
        self._exit_code = 42
        if getattr(self, "_restart_event", None) is not None:
            self._restart_event.set()

    def shutdown(self) -> None:
        if self.connection is not None:
            self.connection.close()
        if getattr(self, "stream", None) is not None:
            self.stream.close()
        self.control.close()
        if self.http is not None:
            self.http.stop()
        self.store.close()
        self.config_store.close()


def build_bot(config: Config, persona: str = "stub", verbose: bool = False) -> Bot:
    """Construct a Bot with the chosen persona. `llm` wires LlmPersona to a local Ollama
    client, reading the active profile's prompts/inference live; `stub` is the no-model
    default used by tests and offline runs."""
    bot = Bot(config, verbose=verbose)
    if persona == "llm":
        from .lore.loader import LoreStore
        from .lore.vector import VectorIndex
        from .lore.wiki import WikiIndex
        from .persona.inference import OllamaInferenceClient
        from .persona.llm import LlmPersona

        inference = (bot.active_profile_doc or {}).get("inference", {})
        client = OllamaInferenceClient(model=inference.get("model"))
        # Knowledge lives under <repo>/knowledge/runtime; resolve from this file, not the CWD.
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _lore_dir = os.path.join(_root, "knowledge", "runtime", "lore")
        _wiki_dir = os.path.join(_root, "knowledge", "runtime", "wiki")
        lore = LoreStore(_lore_dir)
        wiki = WikiIndex(_wiki_dir)
        vector = VectorIndex(_wiki_dir)  # Tier-2 semantic fallback (empty if not built)
        bot.persona = LlmPersona(
            client, lambda: bot.active_profile_doc, lore=lore, wiki=wiki, vector=vector,
            tracer=bot.tracer,
        )
    return bot


async def run_async(config: Config, persona: str = "stub", verbose: bool = False) -> int:
    """Run the daemon; returns its exit code (42 = restart requested, see request_restart)."""
    return await build_bot(config, persona, verbose=verbose).run() or 0
