"""Local control socket. cricket-ctl connects here to drive the same command registry
the in-MUSH admins use. Bound to loopback only.

Wire protocol: newline-delimited JSON. Request: {"cmd": "<name>", "args": [...]}.
Response: one JSON object per request: {"ok": bool, "text": "<joined reply lines>"}.
Console requests run at OPERATOR level.
"""

from __future__ import annotations

import asyncio
import json

from .auth import Level
from .commands.registry import CommandContext


class ControlServer:
    def __init__(self, services, host: str = "127.0.0.1", port: int = 4250) -> None:
        self.s = services
        self.host = host
        self.port = port
        self._server = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._on_client, self.host, self.port
        )

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        async with self._server:
            await self._server.serve_forever()

    def close(self) -> None:
        if self._server is not None:
            self._server.close()

    async def _on_client(self, reader, writer) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                response = await self._handle_request(line)
                writer.write((json.dumps(response) + "\n").encode("utf-8"))
                await writer.drain()
        except (ConnectionResetError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def _handle_request(self, line: bytes) -> dict:
        try:
            req = json.loads(line.decode("utf-8"))
            name = req["cmd"]
            args = req.get("args", [])
        except (ValueError, KeyError, TypeError) as exc:
            return {"ok": False, "text": "bad request: %s" % exc}

        outbox: list = []
        ctx = CommandContext(
            source="console",
            level=Level.OPERATOR,
            reply=outbox.append,
            invoker_name="console",
            bot=self.s,
        )
        result = await self.s.registry.dispatch(name, list(args), ctx)
        return {"ok": result.ok, "text": "\n".join(outbox)}
