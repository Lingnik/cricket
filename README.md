# cricket

A Python bot for a PennMUSH game. It does two separable jobs:

1. **Static logic** -- a deterministic command layer with two front-ends that share one
   registry: a local operator console (`cricket-ctl`) and authorized in-MUSH admins.
2. **Persona** -- an LLM that talks to MUSH users in channel-chat and in-room roleplay
   modes. The LLM backend is pluggable; phase 1 ships a no-model stub.

Design and the persona handoff contract:

- `docs/DESIGN.md` -- architecture, location-config model, commands, RP queue, memory,
  and the verified PennMUSH 1.8.7p0 formats.
- `docs/PERSONA_AFFORDANCES.md` -- the seam the persona session builds against.

## Status (phase 1)

The non-LLM core is functional: connection, line parser, event router, command registry
with permission gating, outbound actions, the control socket, persistent SQLite memory, and
a loopback HTTP control panel that edits persona profiles and drives live control. The
persona is a `StubPersona`; the LLM backend sits behind an abstract `InferenceClient` with
an echo stub -- no model is wired in yet.

Behavior is configured as **persona profiles** in a committed config DB (identity,
per-location engagement/directives, prompts, inference params), editable live over HTTP.
Infrastructure (host/port/account, ports, DB paths) stays in `config.toml` + `.env`.

## Layout

```
cricket/
  cli.py            entry points (run / ctl)
  config.py         infra config: TOML + .env (hosts, ports, DB paths)
  auth.py           permission levels + dbref allowlist
  router.py         events -> commands / persona / RP scene queue
  daemon.py         orchestrator; holds shared runtime state
  control.py        loopback control socket (newline-delimited JSON)
  ctl.py            thin control REPL client
  http_api.py       loopback HTTP control panel + config API (pure route())
  web/app.html      single-page UI (profiles editor + control panel)
  mush/
    events.py       typed events
    protocol.py     line parser (PennMUSH 1.8.7p0 formats)
    connection.py   live TCP/TLS connection (auto-reconnect)
    actions.py      outbound verbs + per-location rate limiting
  commands/
    registry.py     command registry + context + dispatch
    builtins.py     status, mute, say, rp, pose, rpsay, clearqueue, help, reload
  persona/
    base.py         Persona protocol; Turn / Response / ContextLine / BotIdentity
    stub.py         no-model StubPersona
    inference.py    InferenceClient ABC + EchoInferenceClient
    llm.py          LlmPersona (placeholder prompt assembly; phase-2-owned)
  profiles/
    model.py        profile schema, validation, default, derive_runtime
    store.py        ConfigStore -- profiles in the committed config DB
  memory/
    store.py        SQLite memory store (gitignored DB) + MemoryHandle
tests/              pytest suite
data/               config DB (committed) + memory DB (gitignored)
```

## Configure

```
cp .env.example .env                  # fill in host/port/account/password (gitignored)
cp config.example.toml config.toml    # infra: ports, DB paths, global auth grants
```

Behavior (identity, locations, directives, prompts) is not in these files -- it lives in
persona profiles, seeded on first run and edited in the control panel.

## Run

```
python -m cricket run                 # start the daemon (prints the control + panel URLs)
python -m cricket ctl                 # attach the control REPL (try: status, help)
```

Then open the control panel (default `http://127.0.0.1:4280/`) to edit and activate persona
profiles and to drive live control (status, mute, RP toggles, scene queue, recent log).

## Test

From this directory:

```
uv run --with pytest --python C:\Users\evergr3n\.pyenv\pyenv-win\versions\3.13.7\python.exe pytest -q
```

or, with a local interpreter that has pytest:

```
python -m pytest -q
```
