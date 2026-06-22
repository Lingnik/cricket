"""Push-only activity stream server (loopback). Any client that connects receives every
subsequent activity event as a JSON line; it accepts no commands (one-directional, server ->
client). The `ctl` tail subscribes here. Kept separate from the request/response control socket
so streaming never tangles with command dispatch.
"""

from __future__ import annotations

import asyncio
import json


class StreamServer:
    def __init__(self, bus, host: str = "127.0.0.1", port: int = 4252) -> None:
        self.bus = bus
        self.host = host
        self.port = port
        self._server = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._on_client, self.host, self.port)

    async def _on_client(self, reader, writer) -> None:
        def push(evt):
            try:
                writer.write((json.dumps(evt, default=str) + "\n").encode("utf-8"))
            except Exception:
                pass  # best-effort; a stuck viewer must never affect the bot

        cancel = self.bus.subscribe(push)
        try:
            # Hold the connection open; read only to detect the client going away.
            while True:
                data = await reader.read(1024)
                if not data:
                    break
        except (ConnectionResetError, asyncio.CancelledError, OSError):
            pass
        finally:
            cancel()
            try:
                writer.close()
            except OSError:
                pass

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
