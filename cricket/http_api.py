"""Loopback HTTP server: a config editor for persona profiles plus a live control panel.

Runs in a daemon thread beside the asyncio MUSH loop, bound to 127.0.0.1 only. All
request handling lives in the pure function `route(...)` so it is unit-testable without
sockets; the BaseHTTPRequestHandler subclass is a thin adapter.

Reads (status, profile list/doc, queue, log) run in the HTTP thread directly. Mutations
that touch loop-owned state (mute, rp, profile activation/reload) are marshaled onto the
asyncio loop with run_coroutine_threadsafe so the daemon's state has a single writer.

The `bot` object must expose:
    config_store        ConfigStore (thread-safe; its own connections)
    store               MemoryStore (has .path)
    scene_queues        dict[room -> list]
    status_snapshot()   plain dict, safe to call from any thread
    async set_muted(bool) / set_rp(room, bool) / reload_active_profile()
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .memory.store import read_recent_events

_APP_HTML = (Path(__file__).parent / "web" / "app.html").read_text(encoding="utf-8")


def _json(status, payload):
    return status, "application/json", json.dumps(payload).encode("utf-8")


def _run_on_loop(loop, coro, timeout: float = 5.0):
    """Schedule `coro` on the asyncio loop from this (HTTP) thread and await it."""
    return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=timeout)


def route(method: str, path: str, body: bytes, bot, loop):
    """Pure request router. Returns (status, content_type, body_bytes)."""
    split = urlsplit(path)
    parts = [unquote(p) for p in split.path.strip("/").split("/") if p]
    query = parse_qs(split.query)

    # GET / -> the single-page UI.
    if method == "GET" and not parts:
        return 200, "text/html; charset=ascii", _APP_HTML.encode("ascii", "replace")

    if not parts or parts[0] != "api":
        return _json(404, {"error": "not found"})

    api = parts[1:]

    try:
        return _route_api(method, api, query, body, bot, loop)
    except _HttpError as exc:
        return _json(exc.status, {"error": exc.message})
    except ValueError as exc:
        return _json(400, {"error": str(exc)})
    except Exception as exc:  # never leak a stack trace to the client
        return _json(500, {"error": "%s: %s" % (type(exc).__name__, exc)})


class _HttpError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _body_json(body: bytes):
    if not body:
        raise _HttpError(400, "request body required")
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError as exc:
        raise _HttpError(400, "invalid JSON: %s" % exc)


def _route_api(method, api, query, body, bot, loop):
    # /api/status
    if api == ["status"] and method == "GET":
        return _json(200, bot.status_snapshot())

    # /api/mute
    if api == ["mute"] and method == "POST":
        data = _body_json(body)
        snap = _run_on_loop(loop, bot.set_muted(bool(data.get("muted"))))
        return _json(200, snap)

    # /api/harass -- toggle harass-on-connect (a plain bool, set directly like `harass` does)
    if api == ["harass"] and method == "POST":
        data = _body_json(body)
        bot.harass_on_connect = bool(data.get("harass"))
        return _json(200, bot.status_snapshot())

    # /api/memory -- inspect + excise memory ("brain surgery"). The store connection is
    # check_same_thread=False, so direct access from the HTTP thread is safe.
    if api == ["memory"] and method == "GET":
        return _json(200, bot.store.memory_digest())
    if api == ["memory"] and method == "DELETE":
        data = _body_json(body)
        if data.get("room"):
            return _json(200, bot.store.purge_scene(data["room"]))
        if data.get("scope") and data.get("scope_key"):
            n = bot.store.delete_memory(data["scope"], data["scope_key"], data.get("key"))
            return _json(200, {"deleted_rows": n})
        return _json(400, {"error": "provide {room} or {scope, scope_key}"})
    # /api/memory/mask -- soft-redact a scene summary from the context window (keeps it in the DB)
    if api == ["memory", "mask"] and method == "POST":
        data = _body_json(body)
        if not data.get("scope") or not data.get("scope_key"):
            return _json(400, {"error": "provide {scope, scope_key, [key], masked}"})
        n = bot.store.mask_memory(data["scope"], data["scope_key"], data.get("key"),
                                  bool(data.get("masked", True)))
        return _json(200, {"masked_rows": n})

    # /api/events -- the audit trail of received messages/commands (browse + soft-redact).
    if api == ["events"] and method == "GET":
        q = query or {}
        loc = (q.get("location") or [None])[0]
        limit = int((q.get("limit") or ["200"])[0])
        inc = (q.get("include_masked") or ["1"])[0] not in ("0", "false", "")
        return _json(200, {"events": bot.store.list_events(loc, limit, inc)})
    if len(api) == 3 and api[0] == "events" and api[2] == "mask" and method == "POST":
        data = _body_json(body)
        n = bot.store.mask_event(int(api[1]), bool(data.get("masked", True)))
        return _json(200, {"masked_rows": n})

    # /api/profiles
    if api == ["profiles"] and method == "GET":
        active = bot.config_store.active()
        return _json(
            200,
            {
                "active": active[0] if active else None,
                "profiles": bot.config_store.list_profiles(),
            },
        )

    # /api/profiles/{name}[/activate]
    if len(api) >= 2 and api[0] == "profiles":
        name = api[1]
        rest = api[2:]
        if rest == [] and method == "GET":
            doc = bot.config_store.get(name)
            if doc is None:
                return _json(404, {"error": "no such profile: %s" % name})
            return _json(200, doc)
        if rest == [] and method == "PUT":
            doc = _body_json(body)
            bot.config_store.put(name, doc)  # raises ValueError on an invalid doc
            return _json(200, {"saved": name})
        if rest == [] and method == "DELETE":
            bot.config_store.delete(name)
            return _json(200, {"deleted": name})
        if rest == ["activate"] and method == "POST":
            bot.config_store.set_active(name)  # raises ValueError if missing
            snap = _run_on_loop(loop, bot.reload_active_profile())
            return _json(200, snap)

    # /api/rp
    if api == ["rp"] and method == "GET":
        snap = bot.status_snapshot()
        return _json(200, {"rp_enabled": snap.get("rp_enabled", [])})
    if api == ["rp"] and method == "POST":
        data = _body_json(body)
        room = data.get("room")
        if not room:
            return _json(400, {"error": "room required"})
        snap = _run_on_loop(loop, bot.set_rp(room, bool(data.get("enabled"))))
        return _json(200, snap)

    # /api/queue/{room}
    if len(api) == 2 and api[0] == "queue" and method == "GET":
        room = api[1]
        queue = bot.scene_queues.get(room, [])
        lines = [
            {"speaker": c.speaker, "dbref": c.dbref, "kind": c.kind, "text": c.text}
            for c in queue
        ]
        return _json(200, {"room": room, "lines": lines})

    # /api/log?n=50
    if api == ["log"] and method == "GET":
        n = int(query.get("n", ["50"])[0])
        path = getattr(bot.store, "path", None)
        events = read_recent_events(path, n) if path else []
        return _json(200, {"events": events})

    return _json(404, {"error": "not found"})


class _Handler(BaseHTTPRequestHandler):
    # Injected by the server factory.
    bot = None
    loop = None

    def log_message(self, fmt, *args):  # silence default stderr logging
        return

    def _dispatch(self, method):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        status, content_type, payload = route(method, self.path, body, self.bot, self.loop)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")


class HttpConfigServer:
    def __init__(self, bot, host: str, port: int, loop) -> None:
        self.bot = bot
        self.host = host
        self.port = port
        self.loop = loop
        self._server = None
        self._thread = None

    def start(self) -> None:
        handler = type(
            "BoundHandler", (_Handler,), {"bot": self.bot, "loop": self.loop}
        )
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        # Reflect the actual bound port (useful when port 0 is requested in tests).
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="cricket-http", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
