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

## Done (2026-06-21, batch 2)
- **DONE** -- Tier-2 semantic fallback: `tools/build_embeddings.py` (Ollama nomic-embed-text,
  3770 unit vectors) + stdlib `cricket/lore/vector.py` cosine search; wired as the fallback when
  a dossier AND an exact wiki title both miss ("Bazil's lost love" -> the Jasmine reunion log).
- **DONE** -- Web panel redesigned into a real, pleasant single-file CRUD admin
  (`cricket/web/app.html`): profile list, tabbed Identity/Locations/Prompts/Inference editors,
  few-shot pairs, clone/save/activate/delete, live Control panel.
- **DONE** -- Harass-on-connect: `harass on|off` admin command + per-profile default; pages a
  newcomer a personalized insult (the turn is keyed on them, so their dossier is the ammo).
- **DONE** -- Polish: wiki/T2 injection now makes him USE a real detail (Coruscant engages, not
  just "that dump"); self-history clarifies EVP-not-CEO. Ambiguous "Tyler" resolves to Tyler
  Damion (Malign), the correct disambiguation.
- **DONE** -- Goal-aligned eval formalized as the gate: `evals/goal_cases.json` (20 probes) +
  `evals/goals.py` (deterministic temp-0, optional base A/B, JUDGE_PROMPT). Corpus-replay retired.

## Remaining -- next up
- **LATER** -- Hands-on persona tuning via the new CRUD panel (now pleasant; not yet used in
  anger for a real tuning pass).
- **LATER** -- Surface the harass-on-connect toggle and the thinking flag in the web UI (today
  they live in the profile doc / the `harass` command).

## Remaining -- blocked on you / deferred
- **LATER** -- Production go-live: reconfigure to the real `<Cricket>` + room-local `<OOC>`
  channels; point `.env` at the real MUSH (needs real creds).

## Closed (won't do)
- **CLOSED** -- "Clean-mode" safety gate: permanently dropped by product decision -- Cricket is
  fully unhinged on every channel, by design.
- **CLOSED** -- Speaker name-match tightening: not a real problem. Almost every player runs a
  single character (name == character); genuine ambiguity is rare common names like "Tyler",
  which the dossier gazetteer + retrieval already resolve to the right one (e.g. Tyler Damion).
