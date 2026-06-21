# Operations runbook

How to run, restart, test, and inspect Cricket. Companion to `DESIGN.md` (architecture),
`CONFIG.md` (config tiers), `STATUS.md` (plain-language summary), `TODO.md` (open work).

## Pieces and ports
- **Bot daemon** (Windows): `python -m cricket run --persona {stub|llm}`. `llm` = local
  Ollama; `stub` = no model. Connects to the MUSH, and hosts:
  - **Control socket** `127.0.0.1:4250` -- newline-delimited JSON; `python -m cricket ctl`
    attaches a REPL. OPERATOR level. Same command registry as in-MUSH admins.
  - **Web control panel** `http://127.0.0.1:4280/` -- single-page UI: a Profiles editor
    (identity/locations/directives/prompts/few-shot/inference) and a live control panel
    (status, mute, RP toggles, scene queue, recent log). JSON API under `/api/*`.
- **Ollama** (Windows): `http://127.0.0.1:11434`. Model **`cricket-abliterated:latest`**
  (see "Model" below).
- **Test MUSH** (Raspberry Pi): PennMUSH 1.8.7p0 at **`100.88.188.43:4201`** over Tailscale.

## Environment (.env, gitignored)
The daemon's `cli run` loads `.env`:
```
CRICKET_MUSH_HOST=100.88.188.43
CRICKET_MUSH_PORT=4201
CRICKET_MUSH_USE_TLS=false
CRICKET_MUSH_NAME=Cricket
CRICKET_MUSH_PASSWORD=cricketpass
CRICKET_MUSH_CONTROL_PORT=4250
CRICKET_HTTP_PORT=4280
```
The `tools/` scripts read the environment DIRECTLY (they do NOT load `.env`): set
`CRICKET_MUSH_HOST` (defaults to 127.0.0.1) and `CRICKET_TEST_{GOD,CRICKET,BAZIL,BOB}_PW`.
Example:
```
CRICKET_MUSH_HOST=100.88.188.43 CRICKET_TEST_GOD_PW=godpass \
  python tools/mush_admin.py login One godpass "@channel/who Public"
```

## Running / restarting the daemon -- READ THIS
- **Single-instance guard:** a second `run` refuses to start if the control port (4250)
  is bound. Stop the old one first.
- **GOTCHA that bit us repeatedly:** do NOT launch the daemon nested inside another
  backgrounded shell command (`... & python -m cricket run & ...`). It spawns a DUPLICATE
  that also connects as Cricket and double-responds. Always start the daemon as its own
  single background process.
- **Clean restart procedure:**
  1. Kill the running daemon (its python process / the background task).
  2. On the MUSH, clear the stale connection: `python tools/mush_admin.py login One <pw> "@boot Cricket"`.
  3. Start exactly one new daemon: `python -m cricket run --persona llm` (backgrounded, not nested).
- Daemon stdout is buffered; verify state from the MUSH (`@channel/who Public`) or the
  control socket / `/api/status`, not the log file.

## Model (the chat-template fix)
The upstream abliterated GGUF (`hf.co/mlabonne/Meta-Llama-3.1-8B-Instruct-abliterated-GGUF`)
ships a **ChatML** template (`<|im_start|>/<|im_end|>`), which is the WRONG dialect for a
Llama-3.1 model -- it caused stray tokens and character breaks. `ollama/Modelfile` re-creates
it as **`cricket-abliterated`** with the canonical Llama-3.1 template + stop tokens. Rebuild:
```
ollama create cricket-abliterated -f ollama/Modelfile
```
The active profile's `inference.model` points at `cricket-abliterated:latest`.

## Knowledge layout
All lore/knowledge content is colocated under `knowledge/` (reorganized 2026-06-21):
- `knowledge/runtime/lore/` -- loaded live by `LoreStore` (CRICKET.md, CRICKET-HISTORY.md,
  RP-CHARTER.md, voice-exemplars.md, index.json, `dossiers/`).
- `knowledge/runtime/wiki/` -- loaded live by `WikiIndex` + `VectorIndex` (pages/, index.jsonl,
  embeddings.f32, embeddings.meta.jsonl). Built by `tools/build_cache.py` + `tools/build_embeddings.py`.
- `knowledge/sources/players/` -- OOC player-knowledge corpus; distilled INTO `runtime/lore/dossiers/`.
  Not loaded at runtime.
- `knowledge/sources/cricket-logs/wiki/` -- raw RP logs; eval input only (`evals/`), not runtime.

The daemon resolves these from the repo root (`cricket/daemon.py`, `_root`-relative), so it no
longer depends on the launch CWD.

## Config & profiles
- Infra (host/ports/db paths/global auth) is in `config.toml` + `.env`. Behavior is the
  **active persona profile** in the config DB (`data/cricket-config.sqlite3`, committed -- it
  preserves hand-tuning done via the web panel; only the memory DB is gitignored).
- `DEFAULT_PROFILE` in `cricket/profiles/model.py` is the canonical, committed source;
  it seeds a fresh DB. Edit the live profile via the web panel, the `/api/profiles` API, or
  scripts. `tools/wire_persona.py` re-syncs the system prompt (`knowledge/runtime/lore/CRICKET.md`) + few-shot
  (`model.py` `_FEWSHOT`) into the live profile.
- `LlmPersona` reads the active profile LIVE each turn, so prompt/few-shot/inference edits
  apply without a restart. (Changing the MODEL tag needs a restart -- it's set at client
  construction.)

## Tests
```
uv run --with pytest --python "C:/Users/evergr3n/.pyenv/pyenv-win/versions/3.13.7/python.exe" pytest -q tests evals
```
If you hit an `OPENSSL_Applink` crash, `unset SSLKEYLOGFILE` first (a known machine quirk).

## Provisioning a fresh test world
`python tools/mush_admin.py setup` rebuilds the accounts (Cricket #3 NOSPOOF+PARANOID,
Bazil #4 WIZARD admin, Bob #5), the channels (Public/Lounge/OOC), and the global `ooc`
command object. PennMUSH notes: `addcom` is disabled (join via `@channel/on`); the bot is
`PARANOID` so room/connect output is `[Name(#dbref)]`-prefixed (channels are name-only);
new objects default to `NO_COMMAND`; an object can't be name-matched after `@tel` into the
Master Room (set flags first). Run the server: `tailscale ssh kali@100.88.188.43`, then
`cd ~/pennmush/game && ./restart`.

## Scene harness -- driving test characters through a scene
`tools/mush_session_server.py` is a stdlib HTTP server that holds long-lived MUSH connections,
one per character, so you can puppet several at once: send arbitrary commands and read each
character's queued received lines. Scene puppets already exist: **Jessalyn #7, Johanna #8,
Zeak #9** (passwords in `.env`, `CRICKET_TEST_*_PW`). They connect to room `#0` where Cricket is.

Start it (point it at the MUSH):
```
CRICKET_MUSH_HOST=100.88.188.43 python tools/mush_session_server.py   # -> 127.0.0.1:4300
```
API (JSON): `POST /sessions {name,password,[on_connect:[...]]}` -> `{id}`; `POST /sessions/<id>/send
{line}` (or `{lines:[...]}`); `GET /sessions/<id>/recv?wait=N` drains buffered lines (waits up to
N s for Cricket's reply); `GET /sessions`; `DELETE /sessions/<id>`; `GET /health`.

**Memory isolation (so a scene leaves NO trace in real memory).** The daemon's memory DB is
overridable with `CRICKET_MEMORY_DB`. Run a scene against a throwaway DB, then discard it:
```
# 1. stop the real daemon; 2. start it on a scene DB:
CRICKET_MEMORY_DB=data/cricket-memory-scene.sqlite3 python -m cricket run --persona llm
# 3. run the scene through the harness (enable RP for #0 first, e.g. POST /api/rp or an OOC admin)
# 4. stop the daemon; delete the scene DB; restart on the real DB:
rm data/cricket-memory-scene.sqlite3
python -m cricket run --persona llm
```
The events log + scene summaries all land in the scene DB, so deleting it is a complete cleanup.
Keep Bazil OUT of a scene you want to watch live -- log in as Bazil yourself and observe.
