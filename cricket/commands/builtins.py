"""Built-in commands, registered into a Registry.

These run identically from the local console and from authorized in-MUSH admins. The
RP verbs (pose / rpsay) call into the persona with the room's accumulated scene queue;
everything else is deterministic static logic. Handlers reach shared state and services
through ctx.bot (the daemon).
"""

from __future__ import annotations

import re

from ..auth import Level
from ..persona.base import ContextLine, Response, Turn
from .registry import Command, CommandContext

# Lethal / agency-removing action keywords -- the consent gate fires when one co-occurs with a
# player-controlled character in the live scene or the OOC nudges.
# No trailing \b so stems match their inflections ('execut' -> execute/executing).
_MORTAL_RE = re.compile(
    r"\b(kill|murder|execut|behead|maim|cripple|dismember|destroy|vapori[sz]e|incinerat|"
    r"assassinat|slit |disembowel|gut |to death|space (?:him|her|them|you)|put .* down)",
    re.IGNORECASE,
)


def _mortal_intent(bot, room, seed=""):
    """Heuristic pre-gate for CRICKET's own planned lethal/agency-removing action against a
    player-CONTROLLED character. Returns the target's name or None.

    Keys on CRICKET'S intent -- the OOC nudges directed at him and an explicit `!say` seed -- NOT
    on the scene narration (which may mention death without Cricket intending anything; e.g. a
    taser's 'kill setting'). Bot-initiated escalation with no nudge is not caught here (that needs
    the LLM confirmation pass noted in docs/RP-DESIGN.md)."""
    controlled = set(getattr(bot, "scene_owners", {}).get(room, set()))
    if not controlled:
        return None
    texts = [s.get("text", "") for s in getattr(bot, "suggestions", {}).get(room, [])]
    if seed:
        texts.append(seed)
    blob = "\n".join(texts)
    if not _MORTAL_RE.search(blob):
        return None
    low = blob.lower()
    for name in sorted(controlled):
        if name.lower() in low:
            return name
    return None


def _ooc_channel(bot):
    for n, loc in getattr(bot, "locations", {}).items():
        if getattr(loc, "feeds_suggestions", False):
            return n
    return None


def _consent_authorized(ctx, pend) -> bool:
    """Only the named target or an admin may resolve a consent request."""
    if ctx.level >= Level.ADMIN:
        return True
    inv = (getattr(ctx, "invoker_name", "") or "").strip().lower()
    if inv and inv == (pend.get("target", "") or "").strip().lower():
        return True
    ctx.reply("only the target or an admin can resolve consent.")
    return False


def _cast_from_queue(bot, queue) -> list:
    """Distinct speaker names in a scene queue, excluding the bot itself and the
    synthetic 'memory' line."""
    bid = getattr(bot, "bot_identity", None)
    me = (bid.name if bid is not None else "").lower()
    out, seen = [], set()
    for ln in queue:
        s = (getattr(ln, "speaker", "") or "").strip()
        low = s.lower()
        if s and low not in seen and low != me and low != "memory":
            seen.add(low)
            out.append(s)
    return out


async def _set_rp(ctx: CommandContext, room, on: bool) -> None:
    """Toggle RP for a room, running the memory accretion loop at the boundaries:
    on -> recall the prior scene summary; off -> summarize the finished scene + persist."""
    bot = ctx.bot
    if not hasattr(bot, "pending_recall"):
        bot.pending_recall = {}
    bot.scene_queues.setdefault(room, [])
    if on:
        bot.rp_enabled[room] = True
        store = getattr(bot, "store", None)
        summary = store.recall_scene_summary(room) if store is not None else None
        if summary:
            bot.pending_recall[room] = summary
            ctx.reply("rp in %s: True (recalled prior scene)" % room)
        else:
            ctx.reply("rp in %s: True" % room)
        return
    # Finalize: persist what happened, then clear the per-scene state. The running ledger holds
    # the full arc (the verbatim queue may have been byte-trimmed), so prefer it for the summary.
    queue = bot.scene_queues.get(room, [])
    ledger = getattr(bot, "scene_ledger", {}).get(room, [])
    summarizer = getattr(getattr(bot, "persona", None), "summarize_scene", None)
    store = getattr(bot, "store", None)
    if store is not None and (queue or ledger):
        cast = _cast_from_queue(bot, queue)
        summary = ""
        if ledger:
            summary = " ".join(ledger)
        elif summarizer is not None:
            try:
                summary = await summarizer(list(queue), cast=cast)
            except Exception:
                summary = ""
        if summary:
            store.save_scene_summary(room, cast, summary)
    bot.scene_queues[room] = []
    if hasattr(bot, "scene_ledger"):
        bot.scene_ledger.pop(room, None)
    if hasattr(bot, "scene_owners"):
        bot.scene_owners.pop(room, None)
    if hasattr(bot, "suggestions"):
        bot.suggestions.pop(room, None)
    if hasattr(bot, "pending_consent"):
        bot.pending_consent.pop(room, None)
    if hasattr(bot, "consent_granted"):
        bot.consent_granted.pop(room, None)
    bot.pending_recall.pop(room, None)
    bot.rp_enabled[room] = False
    ctx.reply("rp in %s: False" % room)


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


async def cmd_harass(ctx: CommandContext, args: list) -> None:
    if not args or args[0] not in ("on", "off"):
        ctx.reply("usage: harass on|off")
        return
    ctx.bot.harass_on_connect = args[0] == "on"
    ctx.reply("harass_on_connect: %s" % ctx.bot.harass_on_connect)


async def cmd_mem(ctx: CommandContext, args: list) -> None:
    """Inspect / excise memory (the agentic 'brain surgery' CLI):
    `mem` -> digest, `mem show <room>` -> a room's scene summary, `mem purge <room>` -> excise it."""
    store = getattr(ctx.bot, "store", None)
    if store is None:
        ctx.reply("no memory store.")
        return
    sub = args[0].lower() if args else "list"
    if sub in ("list", "digest"):
        d = store.memory_digest()
        out = ["events=%d memory_rows=%d scenes=%d"
               % (d["events"], d["memory_rows"], len(d["scenes"]))]
        for s in d["scenes"][:10]:
            out.append("  [%s] %s" % (s["room"], (s["summary"] or "")[:80]))
        ctx.reply("\n".join(out))
    elif sub == "show" and len(args) >= 2:
        ctx.reply("[%s] %s" % (args[1], store.recall_scene_summary(args[1]) or "(no scene summary)"))
    elif sub == "purge" and len(args) >= 2:
        r = store.purge_scene(args[1])
        ctx.reply("purged %s: %d memory rows, %d events removed"
                  % (r["room"], r["memory_rows_removed"], r["events_removed"]))
    elif sub in ("mask", "unmask") and len(args) >= 2:
        n = store.mask_memory("scene", args[1], masked=(sub == "mask"))
        ctx.reply("%sed scene %s (%d rows) -- %s context"
                  % (sub, args[1], n, "redacted from" if sub == "mask" else "restored to"))
    else:
        ctx.reply("usage: mem [list] | mem show <room> | mem purge <room> | mem mask|unmask <room>")


async def cmd_audit(ctx: CommandContext, args: list) -> None:
    """Browse / redact the audit trail of received messages:
    `audit [n]` -> recent received messages with ids; `audit mask|unmask <id>` -> soft-redact one."""
    store = getattr(ctx.bot, "store", None)
    if store is None:
        ctx.reply("no memory store.")
        return
    if args and args[0].lower() in ("mask", "unmask") and len(args) >= 2:
        try:
            n = store.mask_event(int(args[1]), masked=(args[0].lower() == "mask"))
        except ValueError:
            ctx.reply("usage: audit mask|unmask <event-id>")
            return
        ctx.reply("%sed message #%s (%d rows)" % (args[0].lower(), args[1], n))
        return
    try:
        limit = int(args[0]) if args else 20
    except ValueError:
        limit = 20
    rows = store.list_events(limit=limit)
    out = ["audit trail (newest first):"]
    for e in rows:
        out.append("  #%d @%s [%s] %s%s" % (e["id"], e.get("location"), e.get("kind"),
                                            (e.get("text") or "")[:70], "  [MASKED]" if e.get("masked") else ""))
    ctx.reply("\n".join(out) if rows else "(no events)")


async def cmd_consent_ok(ctx: CommandContext, args: list) -> None:
    room = getattr(ctx.bot, "current_room", None)
    pend = getattr(ctx.bot, "pending_consent", {}).get(room) if room else None
    if not pend:
        ctx.reply("no pending consent.")
        return
    if not _consent_authorized(ctx, pend):
        return
    if hasattr(ctx.bot, "consent_granted"):
        ctx.bot.consent_granted[room] = pend
    ctx.bot.pending_consent.pop(room, None)
    ctx.reply("consent granted for %s." % pend.get("target"))


async def cmd_consent_deny(ctx: CommandContext, args: list) -> None:
    room = getattr(ctx.bot, "current_room", None)
    pend = getattr(ctx.bot, "pending_consent", {}).get(room) if room else None
    if not pend:
        ctx.reply("no pending consent.")
        return
    if not _consent_authorized(ctx, pend):
        return
    ctx.bot.pending_consent.pop(room, None)
    ctx.reply("consent denied for %s; dropping it." % pend.get("target"))


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
    await _set_rp(ctx, room, args[0] == "on")


async def _trigger_rp(ctx: CommandContext, room, force_action, seed_text="") -> None:
    if room is None:
        ctx.reply("no room specified and no current room.")
        return
    # Consent gate: a mortal/agency-removing action against a player-character needs OOC consent
    # FIRST. If a request is pending, block. Otherwise, if intent is detected and not already
    # granted, solicit consent on OOC and block this pose until !consent-ok / !consent-deny.
    pending = getattr(ctx.bot, "pending_consent", {})
    granted = getattr(ctx.bot, "consent_granted", {})
    if pending.get(room):
        ctx.reply("awaiting consent for %s (!consent-ok / !consent-deny)."
                  % pending[room].get("target"))
        return
    target = _mortal_intent(ctx.bot, room, seed_text)
    if target and (granted.get(room, {}).get("target", "") or "").lower() != target.lower():
        ooc = _ooc_channel(ctx.bot)
        msg = ("OOC: I want to do something lethal to %s this round. Target or an admin: "
               "!consent-ok or !consent-deny?" % target)
        if ooc is not None:
            ctx.bot.actions.say_channel(ooc, msg)
        if hasattr(ctx.bot, "pending_consent"):
            ctx.bot.pending_consent[room] = {"target": target}
        ctx.reply("consent requested for %s; blocking pose until resolved." % target)
        return
    queue = ctx.bot.scene_queues.get(room, [])
    context = list(queue)
    # Memory lines (oldest context first): the prior-scene recall (on !rp on) and the running
    # ledger -- the distilled arc that survives byte-trimming of the verbatim tail.
    recall = getattr(ctx.bot, "pending_recall", {}).get(room)
    ledger = getattr(ctx.bot, "scene_ledger", {}).get(room)
    room_desc = getattr(ctx.bot, "current_room_desc", "")
    mem_lines = []
    if room_desc:
        mem_lines.append("The setting (room): %s" % room_desc)
    if recall:
        mem_lines.append("Earlier scene: %s" % recall)
    if ledger:
        mem_lines.append("This scene so far: %s" % " | ".join(ledger))
    suggestions = getattr(ctx.bot, "suggestions", {}).get(room, [])
    if suggestions:
        sline = ["Table talk (OOC nudges -- heed your favorites; weigh, twist, or resist the rest):"]
        for sug in suggestions:
            tag = " [favorite]" if sug.get("favored") else ""
            sline.append("- %s%s: %s" % (sug.get("from", ""), tag, sug.get("text", "")))
        mem_lines.append("\n".join(sline))
    for m in reversed(mem_lines):
        context.insert(0, ContextLine(speaker="memory", dbref=None, kind="emit", text=m))
    turn = Turn(
        mode="rp",
        location=room,
        location_kind="room",
        directives=_directives_for(ctx.bot, room),
        speaker="",
        speaker_dbref="",
        text=seed_text,
        context=context,
        bot_identity=getattr(ctx.bot, "bot_identity", None),
        memory=getattr(ctx.bot, "memory", None),
        # Distillation-refined do-not-puppet names (merged with the persona's gazetteer pass).
        claimed=sorted(getattr(ctx.bot, "scene_owners", {}).get(room, set())),
    )
    resp = await ctx.bot.persona.respond(turn)
    if resp is None:
        ctx.reply("persona stayed silent.")
        return
    action = force_action or resp.action
    _emit(ctx.bot, room, action, resp)
    # Distill the final in-progress block into the ledger, then consume the verbatim scene we
    # just acted on (the ledger retains the arc for the next pose).
    if queue:
        router = getattr(ctx.bot, "router", None)
        if router is not None and hasattr(router, "_ledger_block"):
            router._ledger_block(room, queue[-1])
    ctx.bot.scene_queues[room] = []
    if hasattr(ctx.bot, "suggestions"):
        ctx.bot.suggestions[room] = []  # nudges consumed by this pose
    if hasattr(ctx.bot, "consent_granted"):
        ctx.bot.consent_granted.pop(room, None)  # one-time grant consumed
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
    await _set_rp(ctx, room, args[0] == "on")


async def cmd_bang_clearqueue(ctx: CommandContext, args: list) -> None:
    room = _bot_room(ctx)
    if room is None:
        ctx.reply("no current room.")
        return
    ctx.bot.scene_queues[room] = []
    ctx.reply("cleared scene queue for %s." % room)


async def cmd_help(ctx: CommandContext, args: list) -> None:
    # Role-specific: only commands the invoker's level can actually use.
    available = [c for c in ctx.bot.registry.commands() if ctx.level >= c.level]
    items = [("%s -- %s" % (c.name, c.help)) if c.help else c.name for c in available]
    text = "Cricket commands (%s): %s" % (ctx.level.name, "; ".join(items))
    # In-MUSH: @page the list to the user. Console: reply inline.
    if ctx.source == "mush" and ctx.invoker_name:
        ctx.bot.actions.page(ctx.invoker_name, text)
    else:
        ctx.reply(text)


def _directives_for(bot, location):
    cfg = getattr(bot, "locations", {}).get(location)
    return cfg.directives if cfg is not None else ""


def _emit(bot, room, action, resp: Response) -> None:
    actions = bot.actions
    if action in ("pose", "emit"):
        # SW1 convention: poses are @emit -- raw, self-describing third-person prose, NOT @pose
        # (which would prepend "Cricket"). Always emit raw so output reads like a real SW1 pose.
        actions.emit_room(resp.text)
    elif action == "say":
        actions.say_room(resp.text)
    elif action == "page":
        actions.page(resp.target or room, resp.text)


def register_builtins(registry) -> None:
    registry.register(Command("status", Level.ADMIN, cmd_status, "show bot state"))
    registry.register(Command("mute", Level.ADMIN, cmd_mute, "mute on|off"))
    registry.register(
        Command("harass", Level.ADMIN, cmd_harass, "harass on|off -- insult newcomers on connect")
    )
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
    registry.register(
        Command("mem", Level.ADMIN, cmd_mem,
                "mem [list] | show <room> | purge <room> | mask|unmask <room>")
    )
    registry.register(
        Command("audit", Level.ADMIN, cmd_audit, "audit [n] | audit mask|unmask <event-id>")
    )
    registry.register(Command("help", Level.PUBLIC, cmd_help, "list your commands"))
    registry.register(Command("!help", Level.PUBLIC, cmd_help, "list your commands"))
    # Consent resolution: PUBLIC so the named target (often not an admin) can answer; the
    # handler restricts to the target or an admin.
    for nm in ("consent-ok", "!consent-ok"):
        registry.register(Command(nm, Level.PUBLIC, cmd_consent_ok, "approve a pending mortal action"))
    for nm in ("consent-deny", "!consent-deny"):
        registry.register(Command(nm, Level.PUBLIC, cmd_consent_deny, "deny a pending mortal action"))
