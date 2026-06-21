"""Command registry shared by the console and in-MUSH admins.

Each command declares a minimum Level. A CommandContext carries the invoker's source,
identity, level, a reply() sink, and `bot` (the daemon services). Dispatch enforces the
permission gate before invoking the handler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Union

from ..auth import Level


@dataclass
class Command:
    name: str
    level: Level
    handler: Callable  # async (ctx, args) -> None
    help: str = ""
    triggers_persona: bool = False


@dataclass
class CommandContext:
    """Per-invocation context. `reply` is a synchronous sink for output lines."""

    source: str  # "console" | "mush"
    level: Level
    reply: Callable  # (text: str) -> None
    invoker_dbref: Union[str, None] = None
    invoker_name: str = ""
    bot: Any = None  # daemon services (state, actions, persona, store, ...)
    extra: dict = field(default_factory=dict)


@dataclass
class DispatchResult:
    ok: bool
    error: Union[str, None] = None


class Registry:
    def __init__(self) -> None:
        self._commands: dict = {}

    def register(self, command: Command) -> None:
        self._commands[command.name] = command

    def get(self, name: str) -> Union[Command, None]:
        return self._commands.get(name)

    def names(self) -> list:
        return sorted(self._commands)

    def commands(self) -> list:
        return [self._commands[n] for n in self.names()]

    async def dispatch(self, name: str, args: list, ctx: CommandContext) -> DispatchResult:
        command = self._commands.get(name)
        if command is None:
            ctx.reply("Unknown command: %s" % name)
            return DispatchResult(False, "unknown")
        if ctx.level < command.level:
            ctx.reply("Permission denied.")
            return DispatchResult(False, "denied")
        try:
            await command.handler(ctx, args)
        except Exception as exc:  # surface, do not crash the loop
            ctx.reply("Error: %s" % exc)
            return DispatchResult(False, str(exc))
        return DispatchResult(True, None)
