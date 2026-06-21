# Cricket -- open work

Status: **NEXT** (in progress) / **SOON** / **LATER** / **DEFERRED**. See `STATUS.md` for the
plain-language project summary.

## Persona & voice (the active tuning loop)
- **NEXT** -- IC/OOC context scoping: mode-aware `LoreStore.retrieve(cast, scope)` + two-facet
  dossiers. IC (room RP, `mode=rp`) = only canon-plausible in-universe knowledge; OOC (channels,
  `mode=chat`) = the wider per-player roast/teasing suite. Build the mechanism now; facets fill in
  as richer sheets land.
- **SOON** -- Richer per-player sheets from more wiki logs. (User is fetching them into `corpus/`
  as a separate PR; then distill each into IC + OOC facets.)
- **SOON** -- Tighten the corpus-replay extractor (`evals/replay.py`): its "real next pose"
  reference sometimes grabs narration *about* Cricket. Needed before the eval is a clean yardstick.
- **SOON** -- Make the eval a real loop: wire an actual Opus judge (today `PromptBundleJudge` only
  renders prompts), score before/after on prompt/exemplar changes, add more cases.
- **ONGOING** -- Continue voice tuning (register, specificity) against the eval loop.

## Bot mechanics
- **SOON** -- RP scene-queue management: cap + summarize-old-into-memory (it currently just
  accumulates; `docs/INFERENCE_BACKEND.md` wants an 8-32K working window, summarized not truncated).
- **LATER** -- Memory accretion loop: summarize finished live scenes back into the lore store so his
  memory grows the way the historical logs do (designed, not built).
- **LATER** -- Connection hardening: send-drain is fire-and-forget; reconnect should restore the RP
  room + state; TLS cert policy (only if a production SSL port is used).
- **LATER** -- Harden channel admin auth (name-based today via the PARANOID-populated actors table;
  optional server-side `num(*Name)` resolution).
- **LATER** -- Harass-on-connect / mock-on-reconnect trigger (the connect/disconnect events we just
  started ignoring; the hook point is noted in `router.py`).

## Production / go-live
- **LATER** -- Reconfigure to the real channel model: `<Cricket>` + room-local `<OOC>` (test uses
  Public/Lounge/OOC). Point `.env` at the real MUSH host/port/account.
- **LATER** -- Proper Ollama Modelfile/chat-template fix for this GGUF (we strip stray tokens
  defensively; a correct template would remove the need).
- **DEFERRED** -- "Clean-mode" safety gate (per-channel content filter). All channels unhinged for
  now; soft directives proven insufficient, so this needs a real filter if ever wanted.

## Operational / hygiene
- **SOON** -- Single-instance guard for the daemon (pidfile lock): two daemons connecting as Cricket
  double-respond -- this bit us repeatedly. A start/stop helper would help.
- **SOON** -- Reconcile config-DB commit policy: `DEFAULT_PROFILE` (code) is the committed source of
  truth; the live `data/cricket-config.sqlite3` is runtime state. Decide whether to also commit a DB
  snapshot or keep code canonical.
- **LATER** -- Move test creds out of `tools/` into `.env` so the helper scripts can be committed
  (`tools/` is currently uncommitted because it holds passwords).
- **LATER** -- `.gitattributes` to normalize line endings (silences the CRLF warnings on commit).

## Handoff (phase 2)
- **LATER** -- Update `docs/PERSONA_AFFORDANCES.md` to reflect the lore/few-shot/retrieval reality
  for the separate persona-tuning session, and verify the HTTP control panel can edit
  profiles/prompts/few-shot live (so that session uses the UI, not scripts).
