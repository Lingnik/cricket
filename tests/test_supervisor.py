"""Supervisor OOB restart-socket commands + the daemon `restart` command (no real subprocess)."""

import asyncio
import types

from cricket.supervisor import Supervisor


class FakeChild:
    def __init__(self, pid=999, alive=True):
        self.pid = pid
        self._alive = alive
        self.terminated = False

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated = True
        self._alive = False  # pretend it dies promptly so _terminate_child's poll loop exits


def test_status_reports_child():
    s = Supervisor(["x"])
    s._child = FakeChild(pid=123)
    r = s._handle_cmd("status")
    assert r["ok"] and r["pid"] == 123 and r["alive"] is True


def test_restart_sets_flag_and_terminates_child():
    s = Supervisor(["x"])
    c = FakeChild()
    s._child = c
    r = s._handle_cmd("restart")
    assert r["ok"] and s._restart is True and c.terminated is True


def test_stop_sets_flag_and_terminates_child():
    s = Supervisor(["x"])
    c = FakeChild()
    s._child = c
    r = s._handle_cmd("stop")
    assert r["ok"] and s._stop is True and c.terminated is True


def test_unknown_cmd_is_rejected():
    assert Supervisor(["x"])._handle_cmd("frobnicate")["ok"] is False


def test_supervise_builds_run_child_argv():
    import cricket.supervisor as sup

    captured = {}

    class _Capturing(sup.Supervisor):
        def run(self):
            captured["argv"] = self.child_argv
            return 0

    real = sup.Supervisor
    sup.Supervisor = _Capturing
    try:
        sup.supervise(types.SimpleNamespace(
            persona="llm", config="config.toml", env=".env", port=4251))
    finally:
        sup.Supervisor = real
    argv = captured["argv"]
    assert argv[1:4] == ["-m", "cricket", "run"]
    assert "--persona" in argv and "llm" in argv


def test_cmd_restart_replies_then_schedules_request_restart():
    from cricket.auth import Level
    from cricket.commands import builtins
    from cricket.commands.registry import CommandContext

    fired = {"restart": False}
    bot = types.SimpleNamespace(request_restart=lambda: fired.__setitem__("restart", True))
    replies = []
    ctx = CommandContext(source="console", level=Level.OPERATOR, reply=replies.append, bot=bot)

    async def go():
        await builtins.cmd_restart(ctx, [])
        await asyncio.sleep(0.4)  # let the call_later(0.3, request_restart) fire

    asyncio.run(go())
    assert any("restart" in r.lower() for r in replies)
    assert fired["restart"] is True
