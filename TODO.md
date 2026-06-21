# Cricket -- open work

Status: **NEXT** (in progress) / **SOON** / **LATER** / **DEFERRED** / **DONE**. See
`STATUS.md` for the plain-language summary and `docs/OPERATIONS.md` for the runbook.
The 2026-06-21 overnight "knowledge upgrade" run is logged in `docs/overnight-run.md`.

## Resume context
Everything is on `origin/main` (verified secrets-clean). The bot works end-to-end and
in-character on the Pi test MUSH (`100.88.188.43:4201`) using the fixed `cricket-abliterated`
model; a single live daemon is running. The wiki goldmine (PR #2) is merged and now FULLY
WIRED INTO THE PERSONA: 35 two-facet IC/OOC dossiers, deterministic mentioned-entity retrieval,
a stdlib wiki search engine, and Cricket's own logged self-history. An Opus judge (deterministic
temp-0, with-vs-without retrieval) confirmed the upgrade: engagement 2.6->4.3, grounding
2.3->4.1, voice 3.9->4.5, 7-1-0 head to head. 157 tests+evals green.

## Done (recent -- overnight knowledge upgrade, 2026-06-21)
- **DONE** -- 35 two-facet IC/OOC dossiers distilled from `players/` (31 via workflow + 3
  principals hand-crafted + 6 verify-flagged fixes); contrast-report findings applied
  (Johanna faction, Bazil alias gating). `lore/dossiers/` is the retriever's source of truth.
- **DONE** -- Mentioned-entity retrieval (item **D**): `LoreStore.mentioned()` gazetteer adds
  characters NAMED in a line to the cast, so "what do you know about Johanna?" pulls her dossier
  even when she is absent. The deflection bug is dead (live-verified).
- **DONE** -- Wiki-cache wired into the runtime: stdlib `WikiIndex` (`cricket/lore/wiki.py`)
  over `index.jsonl`; OOC topic injection = the "rogue search engine" (crass summaries of game
  topics, live-verified Biscuit Baron / Coruscant); RP stays canon-grounded.
- **DONE** -- Cricket self-history (`lore/CRICKET-HISTORY.md`, 18 log-grounded exploits) injected
  into the SYSTEM block; he draws on it in RP and brags in OOC.
- **DONE** -- Hidden thinking step implemented (`inference.thinking`, off by default). A/B'd via
  Opus judge: a wash that slightly HURT voice -> kept in code, GATED OFF. Revisit later.
- **DONE** -- Eval loop with Opus judge. NOTE: corpus-replay pose-matching was DEPRECATED as the
  gate (too noisy at temp 0.85/n=10; measures exact-pose-match, not goals). The goal-aligned
  deterministic eval (engagement/grounding/voice) is the trustworthy yardstick.
- **DONE** (earlier) -- memory accretion loop (`_set_rp`: summarize-on-`!rp off`, recall-on-`!rp
  on`); IC/OOC scoping; chat-focus; chat-template fix; single-instance guard; `!help`; hygiene.

## Remaining -- next up
- **SOON** -- Tier-2 vector-search fallback for characters/players with NO curated dossier.
  Tier-1 (curated dossiers) + the keyword/name wiki lookup are done; this adds search-by-meaning
  over `wiki-cache/index.jsonl` (`summary` + `characters[]`). Needs an embedding model (e.g.
  Ollama `nomic-embed-text`) + an index (sqlite-vec/numpy), ideally a small local retrieval
  service to keep the runtime stdlib-only. The thinking step is the natural driver ("do I know
  this person? what do I recall?").
- **SOON** -- Tighten the `retrieve(cast)` speaker name-match: a live player literally named
  "Bazil" still kebab-collides with the "Bazil McKenzie" dossier. (The `mentioned()` path is
  already careful; this is the speakers-present path.)
- **LATER** -- Overnight polish noted by the judge: generic-topic wiki engagement (he dismisses
  "Coruscant" as "that dump" instead of summarizing); occasional over-brag ("I made her CEO" --
  he is EVP). Tunable via prompt/dossier wording.
- **LATER** -- Exercise the web control panel hands-on for live persona tuning (API verified, UI
  not yet used in anger).
- **LATER** -- Broaden the goal-aligned eval set (more subjects/topics/RP probes) and keep it as
  the regression gate.

## Remaining -- blocked on you / deferred
- **LATER** -- Production go-live: reconfigure to the real `<Cricket>` + room-local `<OOC>`
  channels; point `.env` at the real MUSH (needs real creds).
- **DEFERRED** -- "Clean-mode" safety gate (you chose all-unhinged; needs a real filter, not
  polite instructions -- the abliterated model ignores those).
- **DEFERRED** -- Harass-on-connect / mock-on-reconnect (connect/disconnect events ignored; hook
  point noted in `router.py`).
