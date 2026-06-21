# Cricket -- open work

Status: **NEXT** (in progress) / **SOON** / **LATER** / **DEFERRED** / **DONE**. See
`STATUS.md` for the plain-language project summary.

## Done (recent)
- **DONE** -- IC/OOC mode-aware lore scoping (`retrieve(cast, scope)`; two-facet dossiers).
- **DONE** -- Corpus-replay extractor tightened (clean Cricket-led references) + `min_year`
  filter (judge present-day Cricket against present-day logs only).
- **DONE** -- Voice register: softened the "shout often" rule + calm/deadpan exemplars,
  incl. RP-framed ones; live-verified range (dry for mundane, loud when provoked).
- **DONE** -- RP scene-queue cap (60 lines; summarize-into-memory hook documented).
- **DONE** -- Connection hardening: ordered send-drain, opt-in TLS-insecure, reconnect
  restores the RP room key.
- **DONE** -- Single-instance daemon guard (control-port pre-flight).
- **DONE** -- Chat-template fix at the source: the GGUF shipped a wrong ChatML template;
  re-created as `cricket-abliterated` with the canonical Llama-3.1 template (`ollama/Modelfile`).
  Killed the stray-token leaks and improved coherence.
- **DONE** -- Channel-auth hardening: pre-resolve admin dbrefs->names on connect.
- **DONE** -- Hygiene: `.gitattributes`, test creds moved to env (`tools/` committed),
  `PERSONA_AFFORDANCES.md` refreshed, new `docs/CONFIG.md`.

## Remaining -- autonomous
- **NEXT** -- Memory accretion loop: on `!rp off`, summarize the finished scene (LLM call)
  into the memory store keyed by room+cast; on `!rp on`, recall the prior scene summary and
  seed it so Cricket remembers across scenes. (The scene-queue trim hook is already in place.)

## Remaining -- blocked on you / deferred
- **BLOCKED** -- Richer per-player sheets from more wiki logs (your fetch -> `corpus/` PR;
  then distill into the IC/OOC dossier facets).
- **LATER** -- Production go-live: reconfigure to the real `<Cricket>` + room-local `<OOC>`
  channels; point `.env` at the real MUSH (needs real creds).
- **DEFERRED** -- "Clean-mode" safety gate (you chose all-unhinged; needs a real filter).
- **DEFERRED** -- Harass-on-connect / mock-on-reconnect (connect/disconnect events are
  ignored for now; the hook point is noted in `router.py`).

## Eval loop (ongoing)
- The corpus-replay yardstick works; on-brand scoring is an out-of-band Opus pass (the
  harness renders judge prompts). Keep tuning voice against it as data grows.
