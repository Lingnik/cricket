"""WebSocket + oob() inbound transport (see docs/websockets.md).

Connects over WebSocket instead of telnet. World traffic arrives as structured JSON on the
`j` channel -- one object per heard message, carrying the engine-derived speaker dbref (`%#`)
the sender cannot forge -- so attribution is no longer parsed out of spoofable rendered text.
The bot's own solicited command output arrives on the `t` channel, framed by
OUTPUTPREFIX/OUTPUTSUFFIX; outbound commands are `t`-channel frames.

Same interface as mush.connection.Connection (send / connected / run / close, plus the
per-connect setup_commands) with one addition: an `on_event(obj)` callback for the j channel.
PennMUSH multiplexes WS channels in payload byte 0 (src/websock.c): t=text, j=json, p=pueblo,
>=prompt. Client->server frames must be the `t` byte + the command + a trailing newline.
"""

from __future__ import annotations

import asyncio
import json
from typing import Callable, Union

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from .protocol import OUTPUTPREFIX_SENTINEL, OUTPUTSUFFIX_SENTINEL

CH_TEXT = "t"
CH_JSON = "j"


class WsConnection:
    """Async WebSocket MUSH connection with auto-reconnect. `on_line` receives each decoded
    t-channel line (solicited command output); `on_event` receives each parsed j-channel
    JSON object (heard world traffic with a trusted speaker dbref)."""

    def __init__(
        self,
        host: str,
        port: int,
        name: str,
        password: str,
        on_line: Callable,
        on_event: Callable,
        use_tls: bool = False,
        keepalive_seconds: float = 60.0,
        setup_commands: Union[list, None] = None,
        ws_path: str = "/wsclient",
    ) -> None:
        self.host = host
        self.port = port
        self.name = name
        self.password = password
        self.on_line = on_line
        self.on_event = on_event
        self.use_tls = use_tls
        self.keepalive_seconds = keepalive_seconds
        self.setup_commands = list(setup_commands or [])
        self.ws_path = ws_path
        self._ws = None
        self._closing = False
        self._outq = None
        self._writer_task = None
        self._textbuf = ""

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._closing

    @property
    def url(self) -> str:
        scheme = "wss" if self.use_tls else "ws"
        return "%s://%s:%d%s" % (scheme, self.host, self.port, self.ws_path)

    def send(self, text: str) -> None:
        """Queue one command (a t-channel frame) for ordered delivery. Callers stay synchronous;
        the writer task delivers. Internal newlines collapse to spaces -- one frame = one command
        (same rule as the telnet transport, so a multi-line reply can't leak extra commands)."""
        q = self._outq
        if q is None or self._closing:
            return
        one_line = " ".join(text.replace("\r", "\n").split("\n")).strip()
        try:
            q.put_nowait(CH_TEXT + one_line + "\r\n")
        except asyncio.QueueFull:
            pass

    async def _write_loop(self) -> None:
        try:
            while True:
                frame = await self._outq.get()
                try:
                    await self._ws.send(frame)
                except (ConnectionClosed, OSError):
                    break
        except asyncio.CancelledError:
            pass

    def _login(self) -> None:
        self.send("connect %s %s" % (self.name, self.password))
        self.send("OUTPUTPREFIX %s" % OUTPUTPREFIX_SENTINEL)
        self.send("OUTPUTSUFFIX %s" % OUTPUTSUFFIX_SENTINEL)
        for cmd in self.setup_commands:
            self.send(cmd)

    def _on_frame(self, payload) -> None:
        """Demux one WS frame by its leading channel byte."""
        if isinstance(payload, (bytes, bytearray)):
            payload = bytes(payload).decode("latin-1", "replace")
        if not payload:
            return
        ch, body = payload[0], payload[1:]
        if ch == CH_JSON:
            try:
                obj = json.loads(body)
            except ValueError:
                return
            if isinstance(obj, dict):
                self.on_event(obj)
        elif ch == CH_TEXT:
            # The t channel may batch/split lines across frames; buffer and emit complete lines.
            self._textbuf += body
            *complete, self._textbuf = self._textbuf.replace("\r\n", "\n").split("\n")
            for line in complete:
                self.on_line(line)
        # 'p' (pueblo HTML) and '>' (prompt) are ignored.

    async def _read_loop(self) -> None:
        while not self._closing:
            try:
                payload = await self._ws.recv()
            except ConnectionClosed:
                break
            self._on_frame(payload)

    async def _keepalive(self) -> None:
        while not self._closing:
            await asyncio.sleep(self.keepalive_seconds)
            self.send("IDLE")

    async def run(self) -> None:
        """Connect and read until closed, reconnecting with exponential backoff. Each reconnect
        re-runs _login -> setup_commands (re-installs the relay attributes, re-joins channels,
        re-probes the room), so full bot state is restored automatically."""
        backoff = 1.0
        while not self._closing:
            try:
                self._ws = await connect(self.url, max_size=None, open_timeout=15)
                self._outq = asyncio.Queue()
                self._writer_task = asyncio.ensure_future(self._write_loop())
                self._textbuf = ""
                self._login()
                backoff = 1.0
                keepalive = asyncio.ensure_future(self._keepalive())
                try:
                    await self._read_loop()
                finally:
                    keepalive.cancel()
                    await self._teardown()
            except (OSError, ConnectionClosed, asyncio.TimeoutError):
                await self._teardown()
            if self._closing:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)

    async def _teardown(self) -> None:
        if self._writer_task is not None:
            self._writer_task.cancel()
            self._writer_task = None
        self._outq = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except (OSError, ConnectionClosed):
                pass
            self._ws = None

    def close(self) -> None:
        self._closing = True
        if self._ws is not None:
            asyncio.ensure_future(self._teardown())
