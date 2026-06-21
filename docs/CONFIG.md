# Configuration

Cricket's configuration splits into two tiers by how often it changes and who owns it:
**infrastructure** (set once by the operator, in files) and **behavior** (edited live, in a
database). Keeping them apart means you can retune the bot's personality at runtime without
touching wiring or secrets.

## Infrastructure -- `config.toml` + `.env`

The static plumbing the operator sets before starting the daemon:

- `config.toml` (committed, non-secret): the control-socket port, the HTTP control-panel
  bind/host/port, the database paths, and global auth grants (operator/wizard dbrefs).
- `.env` (gitignored, secret): the bot's MUSH host/port/account/password and the
  `CRICKET_TEST_*_PW` test-server credentials. `.env.example` documents every variable; copy
  it to `.env` and fill in. Secrets never go in `config.toml` or in `tools/`.

## Behavior -- persona profiles in the config DB

Everything about how Cricket acts -- his identity, per-location engagement and `directives`,
the `prompts` block (character sheet + few-shot voice anchors), and `inference` params --
lives in **persona profiles** in the committed config DB, `data/cricket-config.sqlite3`.
Exactly one profile is active. Edit a profile through the HTTP control panel or
`PUT /api/profiles/{name}` + activate; `LlmPersona` reads the active profile live, so changes
take effect with no restart. See `docs/PERSONA_AFFORDANCES.md` for the profile shape.

## Commit policy

`DEFAULT_PROFILE` in `cricket/profiles/model.py` is the **canonical, committed source of
truth**. A fresh `data/cricket-config.sqlite3` is seeded from it on first run, so the default
behavior is always reproducible from code under version control.

The live config DB is **runtime state** -- it holds whatever the panel/scripts have edited
since seeding. It is not the authority. To make a live change permanent, fold it back into
`DEFAULT_PROFILE` (and re-seed, or it persists in the runtime DB until reset). This avoids
committing a binary DB that drifts on every edit; the readable Python default stays the record
of intent.

## Key environment variables

- `CRICKET_MUSH_HOST` / `_PORT` / `_USE_TLS` / `_NAME` / `_PASSWORD` -- the bot's MUSH account.
- `CRICKET_MUSH_CONTROL_PORT` (default 4250) -- the local control socket for `cricket-ctl`.
- `CRICKET_HTTP_PORT` (default 4280) -- the local HTTP control panel (loopback only).
- `CRICKET_TEST_GOD_PW` / `_CRICKET_PW` / `_BAZIL_PW` / `_BOB_PW` -- test-server account
  passwords used only by the `tools/` helper scripts.
