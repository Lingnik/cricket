# Cricket -- open work

Status: **NEXT** (in progress) / **SOON** / **LATER** / **DEFERRED** / **DONE**. See
`STATUS.md` for the plain-language summary and `docs/OPERATIONS.md` for the runbook.

## Resume context (post-compact)
Everything is pushed to `origin/main` (verified secrets-clean; GitHub secret-scanning empty).
The bot works end-to-end and in-character on the Pi test MUSH (`100.88.188.43:4201`) using the
fixed `cricket-abliterated` model. Console (`:4250`) and web panel (`:4280`) are live but the
UI hasn't had hands-on use yet. Recent fixes (all committed): chat-template root-cause fix,
chat-focus (engage the latest line + feed the bot its own replies), `!help`, memory accretion,
register tuning, IC/OOC scoping, connection/queue/auth hardening, single-instance guard.

**On resume:** pick up PARALLEL workstreams across this list. A larger **wiki-content PR** is
about to push -- it adds full wiki-cache extraction tooling, headline-character profiles since
2020, and article lookup (eventually arbitrary vector search). When it lands: FIRST distill the
headline-character profiles into the IC/OOC dossier facets (`lore/dossiers/<name>.md` with
`## IC` / `## OOC`), THEN prototype the Tier-2 vector fallback. Known small follow-ups: the lore
name-match is loose (test player "Bazil" pulled the "Bazil McKenzie" dossier); item **D**
(retrieve on MENTIONED entities, not just present cast) is queued behind the wiki PR.

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

## Design directions (next phase, not yet started)
- **Layered retrieval.** The wiki-logs PR brings a full local wiki cache + headline-character
  profiles + article lookup. Add a Tier-2 **vector-search fallback** under `retrieve(cast,
  scope)` for characters/players with no curated dossier. Needs an embedding model (e.g.
  Ollama `nomic-embed-text`) + a real index (sqlite-vec/faiss/numpy) -- likely a small local
  RETRIEVAL SERVICE the bot queries, to keep the runtime dependency-light. Headline-character
  profiles become Tier-1 two-facet (IC/OOC) dossiers.
- **Chain-of-thought "thinking" pre-step.** Optional hidden reasoning pass before generation
  (discarded; only the final pose is posted) to improve scene reasoning / content (distinct
  from few-shot, which fixed voice). Gate behind a profile flag (`inference.thinking`),
  RP-first (~2x latency). MEASURE via corpus-replay before shipping. Natural place to later
  drive Tier-2 retrieval ("do I know this person? what do I recall?").

## Eval loop (ongoing)
- The corpus-replay yardstick works; on-brand scoring is an out-of-band Opus pass (the
  harness renders judge prompts). Keep tuning voice against it as data grows.
