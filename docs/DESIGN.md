# cricket — design

A Python bot for a PennMUSH game. It does two separable jobs:

1. **Static logic** — a deterministic command layer with two front-ends that share one
   registry: a local operator console, and authorized in-MUSH admins/wizards issuing
   commands over a control channel or page.
2. **Persona** — a local LLM that talks to MUSH users, in two modes: **channel chat** and
   **in-room roleplay**. The persona is built and tuned in a *separate* work phase; this
   program only defines the seam it plugs into (see `PERSONA_AFFORDANCES.md`).

The two phases are **the program** (this document) and **the persona** (handoff doc).

## Process topology

```
                    ┌───────────────── cricket daemon (asyncio) ─────────────────┐
  MUSH socket ⇄  Connection ─▶ Parser ─▶ Router ─┬─▶ Command registry ─▶ Actions ─┐
  (telnet)       reconnect,    line →             │   (shared, perm-gated)         │
                 keepalive,    MushEvent          └─▶ Persona (Protocol) ─▶ Actions ┤
                 OUTPUTPREFIX                              │                         │
                                                          ▼                         ▼
  console ⇄ control socket ─▶ Command registry     Inference service        say/pose/@emit/
  (cricket-ctl REPL)                                (separate process,       page → MUSH
                                                     model resident in VRAM)
```

- The bot runs **detached** and stays controllable through a local **control socket**.
  `cricket-ctl` attaches an interactive REPL to it. The console and the in-MUSH admin
  path are two front-ends over the *same* command registry.
- **Inference is a separate process** (model stays resident in VRAM — ~15 GB; spawning
  per message is a non-starter). The persona calls it over localhost HTTP. See
  `PERSONA_AFFORDANCES.md`.

## Layers

- **Connection** (`mush/connection.py`) — TCP socket (optional **TLS**; server has SSL),
  login (`connect <name> <pw>`),
  telnet IAC handling, line buffering, keepalive (`IDLE`), auto-reconnect with backoff,
  re-join channels on reconnect. Issues `OUTPUTPREFIX`/`OUTPUTSUFFIX` so output caused by
  a command the bot *itself* sent is framed and never mistaken for world traffic.
- **Parser** (`mush/protocol.py`) — turns raw lines into typed `MushEvent`s. Most
  server-specific and fragile layer; patterns live in config, are unit-tested against
  captured log samples. Event kinds: `ChannelMessage{channel, speaker, speaker_dbref,
  kind=say|pose|emit, text}`, `Page{sender, sender_dbref, text}`, `RoomSay/RoomPose/
  RoomEmit{speaker, speaker_dbref, text}`, `ConnectNotice`, `CommandEcho` (bracketed by
  OUTPUTPREFIX), `Unknown{raw}`.
- **Router** — looks up the originating location's config (below), then:
  control location → command registry; chat location → engagement policy → persona;
  room → RP queue (see below).
- **Command registry** (`commands/`) — one registry, permission-gated. Each command:
  `{name, level, handler}` where level ∈ `OPERATOR` (console only), `WIZARD`, `ADMIN`
  (allowlisted dbrefs), `PUBLIC`. A `CommandContext` carries source (console|mush),
  invoker dbref/name, and a `reply()` callback (stdout for console; page/channel for
  MUSH). Sensitive commands require **page** (private), never channel, so a spoofed
  `@emit` cannot forge them.
- **Auth** (`auth.py`) — maps **dbref → level** (names are mutable/spoofable; dbref is
  stable). Allowlist lives in gitignored local config.
- **Actions** (`mush/actions.py`) — high-level outbound API: `say_channel`, `pose_room`,
  `emit_room`, `page`, `raw`. Owns comsys formatting and per-location rate limiting /
  flood throttle.
- **Persona seam** (`persona/`) — the daemon depends only on a `Persona` protocol; phase 1
  ships `StubPersona` so the whole pipe runs end-to-end with no model. Full contract in
  `PERSONA_AFFORDANCES.md`.
- **Memory** (`memory/`) — SQLite store, persistent across restarts (below).

## Configuration tiers

Configuration splits into two tiers so that behavior can be edited live while secrets and
wiring stay fixed.

- **Infrastructure** — `config.toml` (non-secret structure) plus `.env` (secrets): MUSH
  host/port/account/password, the control-socket port, the HTTP bind/port, the global
  auth grants, and the two database paths. The operator sets these once; they are read at
  startup.
- **Behavior** — *persona profiles* stored in the committed config DB and edited at
  runtime over HTTP: the bot identity, the per-location engagement/directives, the persona
  prompts, and the inference params. Many named profiles may exist; exactly one is
  **active**, and switching re-derives the bot's behavior live without a restart.

The daemon derives runtime objects from the active profile: a `BotIdentity`, a map of
`LocationConfig`s, and per-location admin grants. `reload_active_profile()` re-derives them
on the asyncio loop after an edit or activation.

## Locations are first-class config objects

Engagement is a property of each place the bot inhabits, not a global mode. Channels and
rooms are configured uniformly, as entries in the active profile's `locations` list.

```json
{
  "name": "Public",            "mode": "chat",
  "engagement": "addressed",   "prefixes": ["cricket,", "hey cricket"],
  "directives": "Keep it PG. Deflect adult themes politely, stay in voice.",
  "rate_limit": "1 / 20s",     "enabled": true,            "admins": []
}
```

A `mode` of `control` makes the location a command channel (no persona); `admins` lists the
dbrefs allowed to drive commands there, page-gated for sensitive ones.

- `directives` is a free-text steering string and is **opaque to phase 1** — it is passed
  through on the `Turn`; phase 2 decides how to fold it into the prompt. It doubles as the
  per-location safety lever ("keep it PG" vs "anything goes") so tone is tuned in config,
  without code changes.
- `engagement`: `always` (respond to all traffic) or `addressed` (respond only when a line
  starts with one of `prefixes`). Per-location `rate_limit` and `enabled` apply.

## Roleplay: queue + explicit trigger

RP happens in **the room the bot currently occupies**, and is **not auto-reactive**:

1. Room traffic (`say`/`pose`/`@emit`) accumulates in a per-room **scene queue** while RP
   is enabled for that room.
2. An admin/wizard fires a verb at the bot — e.g. `ooc CricketBOT !pose` (also `!say`,
   `!rp on|off`, `!clearqueue`). These are commands in the same registry, `ADMIN`/`WIZARD`
   level, whose action type **triggers the persona** with the accumulated queue as scene
   context instead of returning text.
3. The persona returns a pose; Actions emits it; the consumed queue is trimmed.

`!rp on|off` is the per-room listen gate. Manual triggering keeps RP paced and
human-in-the-loop — also the correct safety posture for an uncensored model.

## PennMUSH integration facts (verified against the target server's source)

Target server: **PennMUSH 1.8.7 patchlevel 0** (build 2018-08-10). The reference clone at
`reference/pennmush/` (gitignored) is checked out at tag **`187p0`** — the citations below
are line-accurate to that release, not to `master`.

Bot account is set **`PARANOID`** (and `NOSPOOF`) so spoofable output carries the real
originator, letting the parser attribute every line to a stable dbref.

| Concern | Reality (source @ 187p0) |
|---|---|
| Channel line | `<ChanName> Speaker says, "..."` / `<ChanName> Speaker <pose>` — fmt `"<%s> %s %s"` (`src/extchat.c:3271`); per-channel `@chatformat` can change it |
| Spoof attribution | `NOSPOOF` → `[Name:] ` (`src/notify.c:744`) ; `PARANOID` → `[Name(#dbref)] ` (`src/notify.c:739`), or `[Owner(#d)'s Obj(#d)] ` for owned objects (`:741`) |
| Command framing | `OUTPUTPREFIX` / `OUTPUTSUFFIX` telnet verbs (`hdrs/conf.h:72-73`) |
| Session verbs | `QUIT`, `WHO`, `IDLE` (`hdrs/conf.h:58-66`) |

Server `@config compile` facts that shape the connection layer:

- **SSL support** is compiled in (handled by a slave process) — the bot should support a
  **TLS** connection, not assume plaintext-only.
- Only **limited Unicode** support — treat MUSH I/O as ASCII / Latin-1-safe; do not emit
  multi-byte Unicode.

## Two SQLite databases

State is split across two databases with opposite commit policies, because one holds
shareable configuration and the other holds private conversation content.

- **Config DB** (`data/cricket-config.sqlite3`) — **committed.** Holds persona profiles
  (`profiles(name PK, is_active, doc, updated_ts)`, doc as JSON). Committing it versions and
  backs up the bot's behavior; it carries no secrets (those stay in `.env`). It opens in WAL
  mode with a fresh connection per call, so the asyncio loop and the HTTP thread both touch
  it safely.
- **Memory DB** (`data/cricket-memory.sqlite3`) — **gitignored.** The persistent persona
  memory. Phase 1 owns the schema + read/write API; phase 2 decides what is stored and how
  it enters the prompt. The persona never writes SQL — it gets a memory handle on the `Turn`.

```
actors(dbref PK, name, first_seen, last_seen, flags, notes)
events(id, location, actor_dbref, kind, text, ts)         -- transcript / scene log
memory(scope, scope_key, key, value, updated_ts)          -- persona-writable KV
```

## HTTP control panel

The daemon runs a loopback HTTP server (default `127.0.0.1:4280`) in a thread beside the
asyncio loop. It edits persona profiles and drives live control, so routine operation needs
no CLI. Reads run in the HTTP thread; mutations of loop-owned state are marshaled onto the
loop with `run_coroutine_threadsafe`, keeping the daemon's state single-writer. All request
handling lives in a pure `route()` function for testing without sockets.

| Method + path | Effect |
|---|---|
| `GET /` | the single-page UI (profiles editor + control panel) |
| `GET /api/status` | live status snapshot |
| `POST /api/mute` | `{"muted": bool}` |
| `GET /api/profiles` | active name + list |
| `GET/PUT/DELETE /api/profiles/{name}` | read / validate-and-save / delete a profile doc |
| `POST /api/profiles/{name}/activate` | activate, then re-derive runtime on the loop |
| `GET/POST /api/rp` | read / toggle per-room RP |
| `GET /api/queue/{room}` | the room's scene queue |
| `GET /api/log?n=50` | recent events from the memory DB |

## Safety & repo hygiene (this repo is public)

- **No secrets in git.** Host/port/account/password live in `.env` (gitignored); a committed
  `.env.example` documents the shape. The committed config DB holds profiles only — no
  secrets — and the memory DB (conversation content) is gitignored.
- **All transcripts and LLM I/O** log to the gitignored memory DB / `logs/`.
- **The HTTP panel binds loopback only** (`127.0.0.1`); it is an operator surface, not a
  public one.
- The model is **abliterated — no built-in refusals.** The only safety boundary is what we
  build: per-location `directives`, engagement scoping, rate limits, an instant operator
  **mute**, manual RP triggering, and full I/O logging for review.

## Phase split

| Phase 1 — the program (this session) | Phase 2 — the persona (separate session) |
|---|---|
| Connection, parser, router, command registry, auth, actions, memory store + API | System prompt / character sheet / voice |
| `Persona` protocol, `Turn`/`Response` types, `StubPersona`, smoke harness | `LlmPersona` implementation: prompt construction from `Turn` + memory |
| Profile schema + config DB + HTTP panel + `InferenceClient` seam | Engagement heuristics tuning, RP pacing, sampling params, model choice |
| Location/engagement config schema; `directives` passthrough | Authoring the active profile: identity, `directives`, prompts, inference params |

## Open items (need input)

- Bot's exact MUSH character name (`CricketBOT`? `Cricket`?) and host/port → into `.env`.
- The OOC trigger surface: dedicated OOC channel name vs page, and the exact verb syntax.
- Whether the bot account will have wizard powers (affects what it can set on itself / see).
- Inventory of real channels and which rooms it will RP in.
