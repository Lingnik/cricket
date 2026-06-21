# Cricket -- open work

Status: **NEXT** (in progress) / **SOON** / **LATER** / **DEFERRED** / **DONE**. See
`STATUS.md` for the plain-language summary and `docs/OPERATIONS.md` for the runbook.

## Resume context
Everything is on `origin/main` (verified secrets-clean). The bot works end-to-end and
in-character on the Pi test MUSH (`100.88.188.43:4201`) using the fixed `cricket-abliterated`
model. Console (`:4250`) and web panel (`:4280`) are live but the UI hasn't had hands-on use yet.
Recent fixes: chat-template root-cause fix, chat-focus (engage the latest line + feed the bot its
own replies), `!help`, memory accretion, register tuning, IC/OOC scoping, connection/queue/auth
hardening, single-instance guard.

**The wiki goldmine has LANDED** (PR #2 `players` fast-forwarded onto main 2026-06-21; PR #1 closed
-- its logs already lived at `corpus/wiki/`). New on main:
- `wiki-cache/` -- 7,395 cached SW1-wiki pages + `index.jsonl` (per-page `characters[]` /
  `factions[]` / `rl_date` / `aby_year` / `summary` -- a ready search index) + tooling
  `tools/build_cache.py` / `lookup.py` / `search.py`.
- `players/` -- 35 OOC player-knowledge profiles (cited to the cache). **24 are net-new** (no
  dossier yet); **11 overlap** existing `lore/dossiers/`.
- `docs/contrast/` -- 4 principal contrast reports (cricket, johanna, bazil, crestian) that drove
  the Johanna-faction fix + Bazil-alias gating.

This unblocks the per-player knowledge tiering ("Per-player knowledge" section below). Pick up
PARALLEL workstreams across the list.

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
- **DONE** -- Merged the wiki goldmine (PR #2, fast-forward): `wiki-cache/` (7,395 pages +
  `index.jsonl` search index) + `players/` OOC profile corpus (35) + cache tooling
  (`build_cache`/`lookup`/`search`) + `docs/contrast/` principal reports. PR #1 closed (its
  logs duplicated `corpus/wiki/`).

## Remaining -- autonomous
- **NEXT** -- Memory accretion loop: on `!rp off`, summarize the finished scene (LLM call)
  into the memory store keyed by room+cast; on `!rp on`, recall the prior scene summary and
  seed it so Cricket remembers across scenes. (The scene-queue trim hook is already in place.)

## Per-player knowledge -- the goldmine (unblocked by PR #2)
- **NEXT** -- Distill `players/` profiles into Tier-1 IC/OOC dossier facets that `retrieve(cast,
  scope)` reads (`lore/dossiers/<name>.md`, `## IC` / `## OOC`). **24 net-new** players (no dossier
  yet) + **11 overlaps** to reconcile (the `players/` copy is richer and cited to `wiki-cache/`).
  Decide canonical source: `players/` is the human-authored corpus; `lore/dossiers/` is what the
  retriever reads -- likely generate dossiers FROM `players/` so there is one source of truth.
- **NEXT** -- Apply `docs/contrast/` findings while distilling the 4 principals (cricket, johanna,
  bazil, crestian): Johanna faction correction, Bazil alias gating, etc. Treat the contrast
  reports as the QA pass for principal dossiers; consider extending contrast review to more names.
- **SOON** -- Wire `wiki-cache/index.jsonl` into retrieval (resolve a name -> profile/summary via
  `tools/search.py` / `lookup.py`). This is the shared substrate for BOTH item **D** (retrieve on
  MENTIONED entities, not just present cast -- the "what do you know about Johanna?" gap) and the
  Tier-2 vector fallback below.
- **LATER** -- Tighten the loose dossier name-match (test player "Bazil" pulled "Bazil McKenzie");
  more urgent now that the dossier set is large enough to collide often.

## Remaining -- blocked on you / deferred
- **LATER** -- Production go-live: reconfigure to the real `<Cricket>` + room-local `<OOC>`
  channels; point `.env` at the real MUSH (needs real creds).
- **DEFERRED** -- "Clean-mode" safety gate (you chose all-unhinged; needs a real filter).
- **DEFERRED** -- Harass-on-connect / mock-on-reconnect (connect/disconnect events are
  ignored for now; the hook point is noted in `router.py`).

## Design directions (next phase, not yet started)
- **Layered retrieval.** The local wiki cache + headline profiles + lookup tooling have LANDED
  (see "Per-player knowledge" above). Tier-1 = curated two-facet (IC/OOC) dossiers distilled from
  `players/`. Add a Tier-2 **vector-search fallback** under `retrieve(cast, scope)` for
  characters/players with no curated dossier. `wiki-cache/index.jsonl` (with `summary` +
  `characters[]`) is the corpus to embed. Needs an embedding model (e.g. Ollama
  `nomic-embed-text`) + a real index (sqlite-vec/faiss/numpy) -- likely a small local RETRIEVAL
  SERVICE the bot queries, to keep the runtime dependency-light.
- **Chain-of-thought "thinking" pre-step.** Optional hidden reasoning pass before generation
  (discarded; only the final pose is posted) to improve scene reasoning / content (distinct
  from few-shot, which fixed voice). Gate behind a profile flag (`inference.thinking`),
  RP-first (~2x latency). MEASURE via corpus-replay before shipping. Natural place to later
  drive Tier-2 retrieval ("do I know this person? what do I recall?").

## Eval loop (ongoing)
- The corpus-replay yardstick works; on-brand scoring is an out-of-band Opus pass (the
  harness renders judge prompts). Keep tuning voice against it as data grows.
