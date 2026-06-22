import asyncio

from cricket.auth import Level
from cricket.commands.registry import Command, CommandContext, Registry


def make_ctx(level):
    outbox = []
    ctx = CommandContext(
        source="console", level=level, reply=outbox.append, invoker_name="t"
    )
    return ctx, outbox


def build_registry():
    reg = Registry()
    calls = []

    async def public_handler(ctx, args):
        calls.append(("public", args))
        ctx.reply("ok-public")

    async def admin_handler(ctx, args):
        calls.append(("admin", args))
        ctx.reply("ok-admin")

    reg.register(Command("ping", Level.PUBLIC, public_handler))
    reg.register(Command("secret", Level.ADMIN, admin_handler))
    return reg, calls


def test_public_command_runs_for_public():
    reg, calls = build_registry()
    ctx, out = make_ctx(Level.PUBLIC)
    result = asyncio.run(reg.dispatch("ping", ["a"], ctx))
    assert result.ok
    assert calls == [("public", ["a"])]
    assert out == ["ok-public"]


def test_admin_command_denied_for_public_context():
    reg, calls = build_registry()
    ctx, out = make_ctx(Level.PUBLIC)
    result = asyncio.run(reg.dispatch("secret", [], ctx))
    assert not result.ok
    assert result.error == "denied"
    assert calls == []  # handler never ran
    assert out == ["Permission denied."]


def test_admin_command_runs_for_admin_context():
    reg, calls = build_registry()
    ctx, out = make_ctx(Level.ADMIN)
    result = asyncio.run(reg.dispatch("secret", [], ctx))
    assert result.ok
    assert calls == [("admin", [])]


def test_operator_outranks_admin_requirement():
    reg, calls = build_registry()
    ctx, _ = make_ctx(Level.OPERATOR)
    result = asyncio.run(reg.dispatch("secret", [], ctx))
    assert result.ok


def test_unknown_command():
    reg, _ = build_registry()
    ctx, out = make_ctx(Level.OPERATOR)
    result = asyncio.run(reg.dispatch("nope", [], ctx))
    assert not result.ok
    assert result.error == "unknown"
    assert out == ["Unknown command: nope"]


def test_handler_exception_is_reported_not_raised():
    reg = Registry()

    async def boom(ctx, args):
        raise ValueError("kaboom")

    reg.register(Command("boom", Level.PUBLIC, boom))
    ctx, out = make_ctx(Level.PUBLIC)
    result = asyncio.run(reg.dispatch("boom", [], ctx))
    assert not result.ok
    assert "kaboom" in result.error
    assert out == ["Error: kaboom"]


def test_help_console_is_newline_delimited_one_per_line():
    from types import SimpleNamespace

    from cricket.commands import builtins

    reg = Registry()
    builtins.register_builtins(reg)
    out = []
    ctx = CommandContext(source="console", level=Level.OPERATOR, reply=out.append,
                         bot=SimpleNamespace(registry=reg))
    asyncio.run(builtins.cmd_help(ctx, []))
    text = out[0]
    assert text.startswith("Cricket commands") and "\n" in text  # not "; "-joined
    body = [ln for ln in text.split("\n")[1:] if ln.strip()]
    visible = [c for c in reg.commands() if Level.OPERATOR >= c.level]
    assert len(body) == len(visible)            # exactly one command per line
    assert any("status" in ln for ln in body)
