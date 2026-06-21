"""The live MUSH TCP/TLS connection.

Holds the socket, logs in, frames the session, and feeds raw lines to a callback. The
socket I/O here is exercised against a real server, not unit tests; the testable pieces
(telnet IAC stripping) are factored out as pure functions. Live bits are marked TODO.

On connect the bot sets OUTPUTPREFIX/OUTPUTSUFFIX to the parser's sentinels so output
caused by commands it issues is framed, and (once permissions are settled) should set
itself NOSPOOF + PARANOID so spoofable input carries a real dbref.
"""

from __future__ import annotations

import asyncio
from typing import Callable, Union

from .protocol import OUTPUTPREFIX_SENTINEL, OUTPUTSUFFIX_SENTINEL

IAC = 0xFF
SB = 0xFA
SE = 0xF0


def strip_telnet(data: bytes) -> bytes:
    """Remove telnet IAC command sequences from a byte string. Pure; unit-testable.

    Handles 3-byte WILL/WONT/DO/DONT (0xFB-0xFE) commands, 2-byte commands, and
    IAC SB ... IAC SE subnegotiations.
    """
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b != IAC:
            out.append(b)
            i += 1
            continue
        if i + 1 >= n:
            break
        cmd = data[i + 1]
        if cmd == IAC:  # escaped 0xFF
            out.append(IAC)
            i += 2
        elif cmd == SB:  # subnegotiation: skip to IAC SE
            j = i + 2
            while j + 1 < n and not (data[j] == IAC and data[j + 1] == SE):
                j += 1
            i = j + 2
        elif 0xFB <= cmd <= 0xFE:  # WILL/WONT/DO/DONT + option byte
            i += 3
        else:  # other 2-byte command
            i += 2
    return bytes(out)


class Connection:
    """Async MUSH connection with auto-reconnect. `on_line` is called with each decoded
    text line (no trailing newline)."""

    def __init__(
        self,
        host: str,
        port: int,
        name: str,
        password: str,
        on_line: Callable,
        use_tls: bool = False,
        keepalive_seconds: float = 60.0,
        setup_commands: Union[list, None] = None,
        tls_insecure: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.name = name
        self.password = password
        self.use_tls = use_tls
        # When use_tls is on, certs are verified by default. Set tls_insecure=True ONLY
        # for a MUSH presenting a self-signed cert you trust (it disables verification).
        self.tls_insecure = tls_insecure
        self.on_line = on_line
        self.keepalive_seconds = keepalive_seconds
        # Commands issued right after login on every (re)connect: e.g. setting
        # NOSPOOF/PARANOID and joining channels via @channel/on.
        self.setup_commands = list(setup_commands or [])
        self._reader = None
        self._writer = None
        self._buffer = b""
        self._closing = False
        # Outbound is queued and drained in order by a writer task, so sends are ordered
        # and flushed without blocking the (synchronous) callers. None while disconnected.
        self._outq = None
        self._writer_task = None

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._closing

    def send(self, text: str) -> None:
        """Queue one command line for ordered, drained delivery. Callers stay synchronous;
        the writer task (see `_write_loop`) actually writes and flushes. Latin-1 keeps us
        ASCII/8-bit safe (server has only limited Unicode).

        Internal newlines are collapsed to spaces: each send is exactly ONE command
        terminated by CR-LF. Without this, a multi-line generated reply would make the
        server execute lines 2+ as commands in the bot's room (e.g. a line starting with
        a quote becomes a room `say`), leaking the bot's reply out of the channel.
        """
        q = self._outq
        if q is None or self._closing:
            return  # not connected yet (or shutting down): drop rather than crash
        one_line = " ".join(text.replace("\r", "\n").split("\n")).strip()
        try:
            q.put_nowait((one_line + "\r\n").encode("latin-1", "replace"))
        except asyncio.QueueFull:  # unbounded queue: not expected, but never crash a caller
            pass

    async def _write_loop(self, writer) -> None:
        """Drain the outbound queue in order, flushing after each write so messages are
        not silently buffered. Owns exactly one connection's writer; cancelled on
        disconnect/close."""
        try:
            while True:
                data = await self._outq.get()
                try:
                    writer.write(data)
                    await writer.drain()
                except OSError:
                    break  # connection dropped; run()'s reconnect loop will rebuild it
        except asyncio.CancelledError:
            pass

    async def _open(self) -> None:
        ssl_ctx = None
        if self.use_tls:
            import ssl

            ssl_ctx = ssl.create_default_context()
            if self.tls_insecure:
                # Opt-in only: accept a self-signed MUSH cert. Never the default --
                # verification stays on unless the operator explicitly relaxes it.
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port, ssl=ssl_ctx
        )
        # Fresh per-connection outbound queue + writer task, then log in.
        self._outq = asyncio.Queue()
        self._writer_task = asyncio.ensure_future(self._write_loop(self._writer))
        self._login()

    def _login(self) -> None:
        self.send("connect %s %s" % (self.name, self.password))
        # Frame command output so it is never mistaken for world traffic.
        self.send("OUTPUTPREFIX %s" % OUTPUTPREFIX_SENTINEL)
        self.send("OUTPUTSUFFIX %s" % OUTPUTSUFFIX_SENTINEL)
        # Per-connect setup (idempotent), re-sent on EVERY (re)connect: this is what
        # restores RP state after a reconnect -- it sets NOSPOOF/PARANOID, re-joins every
        # channel via @channel/on, AND re-probes the bot's current room (the
        # `think CRICKET_ROOM=...` command), so channel membership and the scene-queue
        # room key both come back without any extra reconnect bookkeeping.
        for cmd in self.setup_commands:
            self.send(cmd)

    async def _read_loop(self) -> None:
        assert self._reader is not None
        while not self._closing:
            chunk = await self._reader.read(4096)
            if not chunk:
                break
            self._buffer += chunk
            self._buffer = self._dispatch_lines(self._buffer)

    def _dispatch_lines(self, buffer: bytes) -> bytes:
        """Split complete lines out of the buffer, strip telnet, decode, dispatch.
        Returns the unconsumed remainder."""
        cleaned = strip_telnet(buffer)
        # Keep any trailing partial line in the buffer.
        *complete, remainder = cleaned.replace(b"\r\n", b"\n").split(b"\n")
        for raw in complete:
            self.on_line(raw.decode("latin-1"))
        return remainder

    async def _keepalive(self) -> None:
        while not self._closing:
            await asyncio.sleep(self.keepalive_seconds)
            self.send("IDLE")

    async def run(self) -> None:
        """Connect and read until closed, reconnecting with exponential backoff.

        Reconnect restores full bot state: `_open` -> `_login` re-sends `setup_commands`
        on every connect, which re-joins all channels and re-probes the current room, so
        channel membership and RP scene-queue keying come back automatically. (The room's
        accumulated scene-queue *contents* are daemon-side state and are not part of the
        connection; a reconnect mid-scene keeps whatever the daemon already buffered.)"""
        backoff = 1.0
        while not self._closing:
            try:
                await self._open()
                backoff = 1.0
                keepalive = asyncio.ensure_future(self._keepalive())
                try:
                    await self._read_loop()
                finally:
                    keepalive.cancel()
                    self._teardown_writer()
            except OSError:
                self._teardown_writer()
            if self._closing:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)

    def _teardown_writer(self) -> None:
        """Stop the writer task and drop the queue so sends are dropped until reconnect."""
        if self._writer_task is not None:
            self._writer_task.cancel()
            self._writer_task = None
        self._outq = None

    def close(self) -> None:
        self._closing = True
        self._teardown_writer()
        if self._writer is not None:
            self._writer.close()
