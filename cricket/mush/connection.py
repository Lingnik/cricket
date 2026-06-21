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
    ) -> None:
        self.host = host
        self.port = port
        self.name = name
        self.password = password
        self.use_tls = use_tls
        self.on_line = on_line
        self.keepalive_seconds = keepalive_seconds
        self._reader = None
        self._writer = None
        self._buffer = b""
        self._closing = False

    def send(self, text: str) -> None:
        """Write one command line. Latin-1 keeps us ASCII/8-bit safe (server has only
        limited Unicode)."""
        if self._writer is None:
            return
        self._writer.write((text + "\r\n").encode("latin-1", "replace"))
        # TODO(live): schedule drain; low volume tolerates fire-and-forget for now.

    async def _open(self) -> None:
        ssl_ctx = None
        if self.use_tls:
            import ssl

            ssl_ctx = ssl.create_default_context()
            # TODO(live): some MUSH SSL certs are self-signed; make verification a
            # config choice rather than silently relaxing it here.
        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port, ssl=ssl_ctx
        )
        self._login()

    def _login(self) -> None:
        self.send("connect %s %s" % (self.name, self.password))
        # Frame command output so it is never mistaken for world traffic.
        self.send("OUTPUTPREFIX %s" % OUTPUTPREFIX_SENTINEL)
        self.send("OUTPUTSUFFIX %s" % OUTPUTSUFFIX_SENTINEL)
        # TODO(live, needs permissions): self.send("@set me=!NOSPOOF")  # then PARANOID
        # self.send("@set me=PARANOID")

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
        TODO(live): re-join channels and restore room presence after a reconnect."""
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
            except OSError:
                pass
            if self._closing:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)

    def close(self) -> None:
        self._closing = True
        if self._writer is not None:
            self._writer.close()
