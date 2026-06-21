"""The daemon: wires the connection, parser, router, registry, actions, memory, persona,
and control socket into one asyncio process, and holds the shared mutable state that
commands and the router both touch.

The daemon instance IS the `services` object passed to the router and to command
contexts: it exposes config, persona, actions, registry, auth, bot_identity, memory,
store, and the mutable state muted / rp_enabled / scene_queues / recent / current_room.
"""

from __future__ import annotations

import asyncio

from .auth import Allowlist, Level
from .commands.builtins import register_builtins
from .commands.registry import Registry
from .config import Config
from .control import ControlServer
from .memory.store import MemoryHandle, MemoryStore
from .mush.actions import Actions
from .mush.connection import Connection
from .mush.protocol import Parser
from .persona.base import BotIdentity
from .persona.stub import StubPersona
from .router import Router


def build_allowlist(config: Config) -> Allowlist:
    """Build the dbref allowlist from [auth] plus each control location's admins."""
    allow = Allowlist()
    for dbref in config.auth.operators:
        allow.grant(dbref, Level.OPERATOR)
    for dbref in config.auth.wizards:
        allow.grant(dbref, Level.WIZARD)
    for dbref in config.auth.admins:
        allow.grant(dbref, Level.ADMIN)
    for loc in config.locations.values():
        for dbref in loc.admins:
            allow.grant(dbref, Level.ADMIN)
    return allow


class Bot:
    def __init__(self, config: Config, persona=None) -> None:
        self.config = config

        # Persistent state.
        self.store = MemoryStore(config.memory_path)
        self.memory = MemoryHandle(self.store)

        # Identity and authorization.
        self.bot_identity = BotIdentity(name=config.mush.name or "cricket")
        self.auth = build_allowlist(config)

        # Mutable runtime state shared by router + commands.
        self.muted = False
        self.rp_enabled: dict = {}
        self.scene_queues: dict = {}
        self.recent: dict = {}
        self.current_room = None

        # Outbound. The sender is wired to the connection once it exists.
        rate_limits = {
            name: loc.rate_limit
            for name, loc in config.locations.items()
            if loc.rate_limit
        }
        self.actions = Actions(self._send_raw, rate_limits=rate_limits)

        # Persona seam (stub by default; phase 2 swaps in LlmPersona).
        self.persona = persona or StubPersona()

        # Command layer.
        self.registry = Registry()
        register_builtins(self.registry)

        # Event pipeline.
        self.parser = Parser()
        self.router = Router(self)

        # Connection + control socket built in run().
        self.connection = None
        self.control = ControlServer(self, port=config.control.port)

    def _send_raw(self, line: str) -> None:
        if self.connection is not None:
            self.connection.send(line)

    def _on_line(self, line: str) -> None:
        event = self.parser.parse(line)
        if event is None:
            return
        # Fire-and-forget so a slow persona never blocks the read loop.
        asyncio.ensure_future(self.router.handle(event))

    async def run(self) -> None:
        self.connection = Connection(
            host=self.config.mush.host,
            port=self.config.mush.port,
            name=self.config.mush.name,
            password=self.config.mush.password,
            on_line=self._on_line,
            use_tls=self.config.mush.use_tls,
        )
        await self.control.start()
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
        self.store.close()


async def run_async(config: Config) -> None:
    await Bot(config).run()
