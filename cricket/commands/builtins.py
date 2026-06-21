"""Built-in commands, registered into a Registry.

These run identically from the local console and from authorized in-MUSH admins. The
RP verbs (pose / rpsay) call into the persona with the room's accumulated scene queue;
everything else is deterministic static logic. Handlers reach shared state and services
through ctx.bot (the daemon).
"""

from __future__ import annotations

from ..auth import Level
from ..persona.base import Response, Turn
from .registry import Command, CommandContext


def _current_room(ctx: CommandContext, args: list, idx: int):
    """Return the room named at args[idx], or the bot's current room."""
    if len(args) > idx:
        return args[idx]
    return getattr(ctx.bot, "current_room", None)


async def cmd_status(ctx: CommandContext, args: list) -> None:
    bot = ctx.bot
    rp_on = [r for r, on in getattr(bot, "rp_enabled", {}).items() if on]
    ctx.reply("muted: %s" % getattr(bot, "muted", False))
    ctx.reply("current room: %s" % getattr(bot, "current_room", None))
    ctx.reply("rp enabled in: %s" % (", ".join(rp_on) if rp_on else "(none)"))
    queues = getattr(bot, "scene_queues", {})
    sizes = ", ".join("%s=%d" % (r, len(q)) for r, q in queues.items()) or "(none)"
    ctx.reply("scene queues: %s" % sizes)


async def cmd_mute(ctx: CommandContext, args: list) -> None:
    if not args or args[0] not in ("on", "off"):
        ctx.reply("usage: mute on|off")
        return
    ctx.bot.muted = args[0] == "on"
    ctx.reply("muted: %s" % ctx.bot.muted)


async def cmd_reload(ctx: CommandContext, args: list) -> None:
    """Re-derive identity/locations/auth from the active profile in the config DB."""
    apply_fn = getattr(ctx.bot, "_apply_active_profile", None)
    if apply_fn is None:
        ctx.reply("reload unavailable.")
        return
    apply_fn()
    ctx.reply("reloaded active profile: %s" % getattr(ctx.bot, "active_profile", None))


async def cmd_say(ctx: CommandContext, args: list) -> None:
    if len(args) < 2:
        ctx.reply("usage: say <location> <text>")
        return
    location = args[0]
    text = " ".join(args[1:])
    ctx.bot.actions.say_channel(location, text)
    ctx.reply("said on %s." % location)


async def cmd_rp(ctx: CommandContext, args: list) -> None:
    if not args or args[0] not in ("on", "off"):
        ctx.reply("usage: rp on|off [room]")
        return
    room = _current_room(ctx, args, 1)
    if room is None:
        ctx.reply("no room specified and no current room.")
        return
    ctx.bot.rp_enabled[room] = args[0] == "on"
    ctx.bot.scene_queues.setdefault(room, [])
    ctx.reply("rp in %s: %s" % (room, ctx.bot.rp_enabled[room]))


async def _trigger_rp(ctx: CommandContext, room, force_action, seed_text="") -> None:
    if room is None:
        ctx.reply("no room specified and no current room.")
        return
    queue = ctx.bot.scene_queues.get(room, [])
    turn = Turn(
        mode="rp",
        location=room,
        location_kind="room",
        directives=_directives_for(ctx.bot, room),
        speaker="",
        speaker_dbref="",
        text=seed_text,
        context=list(queue),
        bot_identity=getattr(ctx.bot, "bot_identity", None),
        memory=getattr(ctx.bot, "memory", None),
    )
    resp = await ctx.bot.persona.respond(turn)
    if resp is None:
        ctx.reply("persona stayed silent.")
        return
    action = force_action or resp.action
    _emit(ctx.bot, room, action, resp)
    # Consume the scene we just acted on.
    ctx.bot.scene_queues[room] = []
    ctx.reply("posed in %s (%s)." % (room, action))


async def cmd_pose(ctx: CommandContext, args: list) -> None:
    await _trigger_rp(ctx, _current_room(ctx, args, 0), force_action=None)


async def cmd_rpsay(ctx: CommandContext, args: list) -> None:
    await _trigger_rp(ctx, _current_room(ctx, args, 0), force_action="say")


async def cmd_clearqueue(ctx: CommandContext, args: list) -> None:
    room = _current_room(ctx, args, 0)
    if room is None:
        ctx.reply("no room specified and no current room.")
        return
    ctx.bot.scene_queues[room] = []
    ctx.reply("cleared scene queue for %s." % room)


# -- RP trigger verbs (the "!" forms used over the OOC control channel) --------
# These always act on the bot's CURRENT room and treat their args as payload (the
# OOC trigger never passes a room name). The bare pose/rpsay/rp/clearqueue commands
# above keep their optional [room] argument for console use.


def _bot_room(ctx: CommandContext):
    return getattr(ctx.bot, "current_room", None)


async def cmd_bang_pose(ctx: CommandContext, args: list) -> None:
    await _trigger_rp(ctx, _bot_room(ctx), force_action="pose")


async def cmd_bang_say(ctx: CommandContext, args: list) -> None:
    await _trigger_rp(ctx, _bot_room(ctx), force_action="say", seed_text=" ".join(args))


async def cmd_bang_rp(ctx: CommandContext, args: list) -> None:
    if not args or args[0] not in ("on", "off"):
        ctx.reply("usage: !rp on|off")
        return
    room = _bot_room(ctx)
    if room is None:
        ctx.reply("no current room.")
        return
    ctx.bot.rp_enabled[room] = args[0] == "on"
    ctx.bot.scene_queues.setdefault(room, [])
    ctx.reply("rp in %s: %s" % (room, ctx.bot.rp_enabled[room]))


async def cmd_bang_clearqueue(ctx: CommandContext, args: list) -> None:
    room = _bot_room(ctx)
    if room is None:
        ctx.reply("no current room.")
        return
    ctx.bot.scene_queues[room] = []
    ctx.reply("cleared scene queue for %s." % room)


async def cmd_help(ctx: CommandContext, args: list) -> None:
    available = [
        c for c in ctx.bot.registry.commands() if ctx.level >= c.level
    ]
    ctx.reply("commands: " + ", ".join(c.name for c in available))


def _directives_for(bot, location):
    cfg = getattr(bot, "locations", {}).get(location)
    return cfg.directives if cfg is not None else ""


def _emit(bot, room, action, resp: Response) -> None:
    actions = bot.actions
    if action == "pose":
        actions.pose_room(resp.text)
    elif action == "emit":
        actions.emit_room(resp.text)
    elif action == "say":
        actions.say_room(resp.text)
    elif action == "page":
        actions.page(resp.target or room, resp.text)


def register_builtins(registry) -> None:
    registry.register(Command("status", Level.ADMIN, cmd_status, "show bot state"))
    registry.register(Command("mute", Level.ADMIN, cmd_mute, "mute on|off"))
    registry.register(Command("reload", Level.OPERATOR, cmd_reload, "reload config"))
    registry.register(Command("say", Level.ADMIN, cmd_say, "say <location> <text>"))
    registry.register(Command("rp", Level.ADMIN, cmd_rp, "rp on|off [room]"))
    registry.register(
        Command("pose", Level.ADMIN, cmd_pose, "pose [room]", triggers_persona=True)
    )
    registry.register(
        Command("rpsay", Level.ADMIN, cmd_rpsay, "rpsay [room]", triggers_persona=True)
    )
    registry.register(
        Command("clearqueue", Level.ADMIN, cmd_clearqueue, "clearqueue [room]")
    )
    # RP trigger verbs over OOC ("Cricket !pose"), acting on the current room.
    registry.register(
        Command("!pose", Level.ADMIN, cmd_bang_pose, "RP pose from the scene queue",
                triggers_persona=True)
    )
    registry.register(
        Command("!say", Level.ADMIN, cmd_bang_say, "!say <text> -- RP say",
                triggers_persona=True)
    )
    registry.register(Command("!rp", Level.ADMIN, cmd_bang_rp, "!rp on|off"))
    registry.register(
        Command("!clearqueue", Level.ADMIN, cmd_bang_clearqueue, "clear the scene queue")
    )
    registry.register(Command("help", Level.PUBLIC, cmd_help, "list commands"))
