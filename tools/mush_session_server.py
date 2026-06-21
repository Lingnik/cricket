"""Long-lived MUSH session harness -- a small stdlib HTTP server that holds persistent
connections to the test MUSH (one per character) so an operator (or an agent) can drive
several characters at once: send arbitrary commands and read the queued received lines.

Built to play test characters (e.g. Jessalyn, Johanna, Zeak) through a scene against Cricket.
Pair it with a throwaway memory DB (CRICKET_MEMORY_DB) so the scene leaves no trace in the
bot's real memory -- see docs/OPERATIONS.md "Scene harness".

    python tools/mush_session_server.py            # serve on 127.0.0.1:4300

HTTP API (all JSON):
    POST   /sessions            {name, password, [host, port], [on_connect: [cmd,...]]}
                                 -> {id, name, alive}   (connects + runs on_connect cmds)
    GET    /sessions            -> [{id, name, alive, buffered}, ...]
    POST   /sessions/<id>/send  {line}  or  {lines: [cmd, ...]}      -> {ok, sent}
    GET    /sessions/<id>/recv  [?wait=N][?peek=1]  -> {lines: [...], alive}
                                 drains the queue; wait=N blocks up to N s for the first line
    DELETE /sessions/<id>       -> {closed: id}        (sends QUIT, closes the socket)
    GET    /health              -> {ok, sessions}

No credentials live in this file; pass them per request (read them from .env yourself).
"""

from __future__ import annotations

import collections
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# Reuse the telnet IAC stripper from the admin tool (same directory).
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mush_admin import strip_iac  # noqa: E402

DEFAULT_HOST = os.environ.get("CRICKET_MUSH_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("CRICKET_MUSH_PORT", "4201"))
BIND_HOST = os.environ.get("MUSH_SESSION_HOST", "127.0.0.1")
BIND_PORT = int(os.environ.get("MUSH_SESSION_PORT", "4300"))


def _split_lines(textbuf: str, data: bytes):
    """Strip telnet IAC from a recv chunk, append to the carry-over textbuf, and split out
    complete lines (dropping the MUSH's blank formatting lines). Returns (lines, remaining_textbuf)
    where remaining_textbuf is the trailing partial line carried to the next chunk."""
    textbuf += strip_iac(data).decode("latin-1", "replace")
    lines = []
    while "\n" in textbuf:
        line, textbuf = textbuf.split("\n", 1)
        line = line.rstrip("\r")
        if line.strip():
            lines.append(line)
    return lines, textbuf


class Session:
    """One long-lived MUSH connection with a background reader buffering received lines."""

    def __init__(self, sid: str, name: str, host: str, port: int):
        self.id = sid
        self.name = name
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.settimeout(0.4)
        self._buf = collections.deque(maxlen=10000)
        self._lock = threading.Lock()
        self._textbuf = ""
        self.alive = True
        self._reader = threading.Thread(target=self._read_loop, name="recv-%s" % sid, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        while self.alive:
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                self.alive = False
                break
            if not data:
                self.alive = False
                break
            new_lines, self._textbuf = _split_lines(self._textbuf, data)
            if new_lines:
                with self._lock:
                    self._buf.extend(new_lines)

    def send(self, line: str) -> None:
        self.sock.sendall((line + "\r\n").encode("latin-1"))

    def drain(self, peek: bool = False) -> list:
        with self._lock:
            lines = list(self._buf)
            if not peek:
                self._buf.clear()
        return lines

    def buffered(self) -> int:
        with self._lock:
            return len(self._buf)

    def close(self) -> None:
        self.alive = False
        try:
            self.sock.sendall(b"QUIT\r\n")
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


# Session registry (shared across handler threads).
_SESSIONS: dict = {}
_REG_LOCK = threading.Lock()
_NEXT = [1]


def _new_session(name: str, password: str, host: str, port: int, on_connect: list) -> dict:
    with _REG_LOCK:
        sid = "s%d" % _NEXT[0]
        _NEXT[0] += 1
    sess = Session(sid, name, host, port)
    time.sleep(0.5)  # let the connect banner arrive
    sess.send("connect %s %s" % (name, password))
    time.sleep(0.8)  # let the login result + initial room/channel output arrive
    for cmd in on_connect or []:
        sess.send(cmd)
        time.sleep(0.3)
    with _REG_LOCK:
        _SESSIONS[sid] = sess
    return {"id": sid, "name": name, "alive": sess.alive}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet; this is a dev tool
        pass

    def _json(self, code: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _parts(self):
        return [p for p in urlparse(self.path).path.split("/") if p]

    def do_GET(self):
        parts = self._parts()
        if parts == ["health"]:
            return self._json(200, {"ok": True, "sessions": list(_SESSIONS)})
        if parts == ["sessions"]:
            out = [
                {"id": s.id, "name": s.name, "alive": s.alive, "buffered": s.buffered()}
                for s in _SESSIONS.values()
            ]
            return self._json(200, out)
        if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "recv":
            sess = _SESSIONS.get(parts[1])
            if sess is None:
                return self._json(404, {"error": "no such session"})
            q = parse_qs(urlparse(self.path).query)
            peek = q.get("peek", ["0"])[0] not in ("0", "", "false")
            wait = float(q.get("wait", ["0"])[0] or 0)
            deadline = time.time() + wait
            while wait > 0 and sess.buffered() == 0 and sess.alive and time.time() < deadline:
                time.sleep(0.2)
            return self._json(200, {"lines": sess.drain(peek=peek), "alive": sess.alive})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        parts = self._parts()
        if parts == ["sessions"]:
            d = self._body()
            name, password = d.get("name"), d.get("password")
            if not name or not password:
                return self._json(400, {"error": "name and password required"})
            try:
                info = _new_session(
                    name, password,
                    d.get("host", DEFAULT_HOST), int(d.get("port", DEFAULT_PORT)),
                    d.get("on_connect", []),
                )
            except OSError as exc:
                return self._json(502, {"error": "connect failed: %s" % exc})
            return self._json(200, info)
        if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "send":
            sess = _SESSIONS.get(parts[1])
            if sess is None:
                return self._json(404, {"error": "no such session"})
            if not sess.alive:
                return self._json(409, {"error": "session not alive"})
            d = self._body()
            lines = d.get("lines") or ([d["line"]] if d.get("line") is not None else [])
            for ln in lines:
                sess.send(ln)
                time.sleep(0.15)
            return self._json(200, {"ok": True, "sent": len(lines)})
        return self._json(404, {"error": "not found"})

    def do_DELETE(self):
        parts = self._parts()
        if len(parts) == 2 and parts[0] == "sessions":
            with _REG_LOCK:
                sess = _SESSIONS.pop(parts[1], None)
            if sess is None:
                return self._json(404, {"error": "no such session"})
            sess.close()
            return self._json(200, {"closed": parts[1]})
        return self._json(404, {"error": "not found"})


def main() -> int:
    srv = ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    print("mush session harness on http://%s:%d (MUSH %s:%d)" % (BIND_HOST, BIND_PORT, DEFAULT_HOST, DEFAULT_PORT))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for s in list(_SESSIONS.values()):
            s.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
