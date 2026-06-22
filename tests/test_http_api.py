import asyncio
import json
import threading
import urllib.request
from types import SimpleNamespace

import pytest

from cricket.http_api import HttpConfigServer, route
from cricket.memory.store import MemoryStore
from cricket.persona.base import ContextLine
from cricket.profiles import DEFAULT_PROFILE, ConfigStore


class FakeBot:
    def __init__(self, tmp_path):
        self.config_store = ConfigStore(str(tmp_path / "config.sqlite3"))
        self.config_store.seed_default_if_empty(DEFAULT_PROFILE)
        self.store = MemoryStore(str(tmp_path / "memory.sqlite3"))
        self.scene_queues = {}
        self.muted = False
        self.harass_on_connect = False
        self.rp_enabled = {}
        self.current_room = None
        self.locations = {}

    def status_snapshot(self):
        active = self.config_store.active()
        return {
            "connected": False,
            "muted": self.muted,
            "harass_on_connect": self.harass_on_connect,
            "active_profile": active[0] if active else None,
            "rp_enabled": [r for r, on in self.rp_enabled.items() if on],
            "scene_queue_sizes": {r: len(q) for r, q in self.scene_queues.items()},
            "current_room": self.current_room,
            "location_count": len(self.locations),
        }

    async def set_muted(self, muted):
        self.muted = bool(muted)
        return self.status_snapshot()

    async def set_rp(self, room, enabled):
        self.rp_enabled[room] = bool(enabled)
        self.scene_queues.setdefault(room, [])
        return self.status_snapshot()

    async def reload_active_profile(self):
        return self.status_snapshot()


def body(result):
    """Decode the JSON body from a route() result tuple."""
    return json.loads(result[2].decode("utf-8"))


@pytest.fixture
def loop():
    lp = asyncio.new_event_loop()
    t = threading.Thread(target=lp.run_forever, daemon=True)
    t.start()
    yield lp
    lp.call_soon_threadsafe(lp.stop)
    t.join(timeout=2)


# -- reads (no loop needed) ----------------------------------------------------
def test_index_serves_html(tmp_path):
    bot = FakeBot(tmp_path)
    status, ctype, payload = route("GET", "/", b"", bot, None)
    assert status == 200
    assert "text/html" in ctype
    assert b"Cricket Control" in payload


def test_status(tmp_path):
    bot = FakeBot(tmp_path)
    status, _, _ = route("GET", "/api/status", b"", bot, None)
    assert status == 200


def test_profiles_list(tmp_path):
    bot = FakeBot(tmp_path)
    result = route("GET", "/api/profiles", b"", bot, None)
    assert result[0] == 200
    data = body(result)
    assert data["active"] == "default"
    assert data["profiles"] == ["default"]


def test_get_profile(tmp_path):
    bot = FakeBot(tmp_path)
    result = route("GET", "/api/profiles/default", b"", bot, None)
    assert result[0] == 200
    assert body(result)["identity"]["presented_name"] == "Cricket"


def test_get_missing_profile(tmp_path):
    bot = FakeBot(tmp_path)
    assert route("GET", "/api/profiles/nope", b"", bot, None)[0] == 404


def test_put_profile_valid(tmp_path):
    bot = FakeBot(tmp_path)
    payload = json.dumps(DEFAULT_PROFILE).encode("utf-8")
    result = route("PUT", "/api/profiles/alpha", payload, bot, None)
    assert result[0] == 200
    assert "alpha" in bot.config_store.list_profiles()


def test_put_profile_invalid_is_400(tmp_path):
    bot = FakeBot(tmp_path)
    bad = json.loads(json.dumps(DEFAULT_PROFILE))
    bad["locations"][0]["mode"] = "bogus"
    result = route("PUT", "/api/profiles/bad", json.dumps(bad).encode("utf-8"), bot, None)
    assert result[0] == 400
    assert "error" in body(result)
    assert "bad" not in bot.config_store.list_profiles()


def test_delete_profile(tmp_path):
    bot = FakeBot(tmp_path)
    route("PUT", "/api/profiles/alpha", json.dumps(DEFAULT_PROFILE).encode(), bot, None)
    assert route("DELETE", "/api/profiles/alpha", b"", bot, None)[0] == 200
    assert bot.config_store.get("alpha") is None


def test_unknown_path_404(tmp_path):
    bot = FakeBot(tmp_path)
    assert route("GET", "/api/bogus", b"", bot, None)[0] == 404


def test_queue(tmp_path):
    bot = FakeBot(tmp_path)
    bot.scene_queues["Room1"] = [
        ContextLine(speaker="Bob", dbref="#9", kind="say", text="hi")
    ]
    result = route("GET", "/api/queue/Room1", b"", bot, None)
    assert result[0] == 200
    lines = body(result)["lines"]
    assert lines == [{"speaker": "Bob", "dbref": "#9", "kind": "say", "text": "hi"}]


def test_log(tmp_path):
    bot = FakeBot(tmp_path)
    store = MemoryStore(bot.store.path)
    store.log_event("Public", "#9", "say", "hello world")
    store.close()
    result = route("GET", "/api/log?n=10", b"", bot, None)
    assert result[0] == 200
    events = body(result)["events"]
    assert events and events[-1]["text"] == "hello world"


# -- mutations (need a running loop) -------------------------------------------
def test_mute(tmp_path, loop):
    bot = FakeBot(tmp_path)
    result = route("POST", "/api/mute", json.dumps({"muted": True}).encode(), bot, loop)
    assert result[0] == 200
    assert body(result)["muted"] is True
    assert bot.muted is True


def test_memory_digest_and_purge(tmp_path, loop):
    bot = FakeBot(tmp_path)
    # seed a scene memory + a logged event for room #0
    bot.store.save_scene_summary("#0", ["Johanna"], "Johanna threatened Cricket.")
    bot.store.log_event("#0", "#8", "pose", "Johanna draws her sidearm.")
    dig = body(route("GET", "/api/memory", None, bot, loop))
    assert dig["events"] == 1
    assert any(s["room"] == "#0" for s in dig["scenes"])
    # excise the scene
    res = body(route("DELETE", "/api/memory", json.dumps({"room": "#0"}).encode(), bot, loop))
    assert res["events_removed"] == 1 and res["memory_rows_removed"] >= 1
    dig2 = body(route("GET", "/api/memory", None, bot, loop))
    assert dig2["events"] == 0 and dig2["scenes"] == []


def test_audit_log_and_masking(tmp_path, loop):
    bot = FakeBot(tmp_path)
    e1 = bot.store.log_event("#0", "#8", "pose", "Johanna draws her sidearm.")
    bot.store.log_event("#0", "#9", "say", "Zeak grins.")
    # audit trail shows both received messages, each with a masked flag
    ev = body(route("GET", "/api/events", None, bot, loop))["events"]
    assert len(ev) == 2 and all("masked" in e for e in ev)
    # mask e1 -> excluded from context reads, but kept in the full audit trail
    body(route("POST", "/api/events/%d/mask" % e1, json.dumps({"masked": True}).encode(), bot, loop))
    assert all(r["text"] != "Johanna draws her sidearm." for r in bot.store.recent_events("#0"))
    full = body(route("GET", "/api/events?include_masked=1", None, bot, loop))["events"]
    active = body(route("GET", "/api/events?include_masked=0", None, bot, loop))["events"]
    assert len(full) == 2 and len(active) == 1  # redacted from active, preserved in the trail
    # masking a scene summary redacts it from the context window (recall returns nothing)
    bot.store.save_scene_summary("#0", ["Johanna"], "Johanna threatened Cricket.")
    assert bot.store.recall_scene_summary("#0") == "Johanna threatened Cricket."
    body(route("POST", "/api/memory/mask",
               json.dumps({"scope": "scene", "scope_key": "#0", "masked": True}).encode(), bot, loop))
    assert bot.store.recall_scene_summary("#0") is None


def test_harass_toggle(tmp_path, loop):
    bot = FakeBot(tmp_path)
    result = route("POST", "/api/harass", json.dumps({"harass": True}).encode(), bot, loop)
    assert result[0] == 200
    assert body(result)["harass_on_connect"] is True
    assert bot.harass_on_connect is True
    result = route("POST", "/api/harass", json.dumps({"harass": False}).encode(), bot, loop)
    assert body(result)["harass_on_connect"] is False
    assert bot.harass_on_connect is False


def test_rp_toggle(tmp_path, loop):
    bot = FakeBot(tmp_path)
    result = route(
        "POST", "/api/rp", json.dumps({"room": "Room1", "enabled": True}).encode(), bot, loop
    )
    assert result[0] == 200
    assert "Room1" in body(result)["rp_enabled"]


def test_rp_requires_room(tmp_path, loop):
    bot = FakeBot(tmp_path)
    result = route("POST", "/api/rp", json.dumps({"enabled": True}).encode(), bot, loop)
    assert result[0] == 400


def test_activate_profile(tmp_path, loop):
    bot = FakeBot(tmp_path)
    route("PUT", "/api/profiles/alpha", json.dumps(DEFAULT_PROFILE).encode(), bot, None)
    result = route("POST", "/api/profiles/alpha/activate", b"", bot, loop)
    assert result[0] == 200
    assert body(result)["active_profile"] == "alpha"
    assert bot.config_store.active()[0] == "alpha"


def test_activate_unknown_is_400(tmp_path, loop):
    bot = FakeBot(tmp_path)
    assert route("POST", "/api/profiles/nope/activate", b"", bot, loop)[0] == 400


# -- one end-to-end pass over a real socket ------------------------------------
def test_server_integration(tmp_path, loop):
    bot = FakeBot(tmp_path)
    server = HttpConfigServer(bot, "127.0.0.1", 0, loop)
    server.start()
    try:
        base = "http://127.0.0.1:%d" % server.port
        with urllib.request.urlopen(base + "/api/status") as r:
            assert r.status == 200
            assert json.loads(r.read())["muted"] is False
        with urllib.request.urlopen(base + "/") as r:
            assert b"Cricket Control" in r.read()
    finally:
        server.stop()
