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

## Done (2026-06-21, batch 3 -- RP architecture + scene-replay eval)
- **DONE** -- Full RP rework (see `docs/RP-DESIGN.md` + `lore/RP-CHARTER.md`): RP-1 block-grouping
  of multiline poses; RP-2 byte-budgeted scene tail + append-only per-block distillation ledger
  (retired SCENE_QUEUE_CAP; `inference.rp_context_bytes`); RP-3 charter injection (RP turns only)
  + shared-history (his logged scenes with the present cast) + room-description probe; RP-4
  do-not-puppet set (deterministic dbref/gazetteer + distillation-extracted actors) + unknown-cast
  wiki prefetch; RP-5 OOC->RP suggestion bridge (`feeds_suggestions` channel; favorites heeded);
  RP-6 consent gate (`!consent-ok`/`!consent-deny`, OOC request FIRST, block pose-gen until
  resolved; keys on Cricket's intent/nudges, NOT scene narration; NPCs exempt).
- **DONE** -- SW1 `@emit` poses: RP output is always a raw `@emit` (self-describing third person),
  never `@pose`/name-prefixed.
- **DONE** -- Standing system rules: anti-fabrication (deflect, don't invent canon), recount (tell
  ONE event, no splicing), novelty (examples show VOICE not a script -- killed verbatim catchphrase
  parroting, e.g. 'FUCK THE POLICE' 2->0 in the 12-scene eval).
- **DONE** -- `evals/scene_replay.py`: feeds a real multi-party log's lead-up through the FULL RP
  stack (grouping -> ledger -> dossiers/do-not-puppet -> `_trigger_rp`) and prints the generated
  next pose vs the actual one; `--report` writes JSON for an Opus judge; `--list` shows cut points.
  It exposed + we fixed: null poses (consent-gate false-positive on 'kill setting' narration),
  distillation junk-actor/preamble leaks. Uses the full live retrieval (dossiers = distilled player
  profiles, wiki, T2) + fabricated dbrefs/room-desc (logs lack PARANOID tags, by nature).

## Remaining -- next up
- **NEXT** -- RP pose-quality tuning (scene-replay baseline ~voice 2.7 / fit 2.7 / quality 2.5 /5;
  the eval is NOISY at temp 0.85, so trust direction not 0.2 deltas -- use temp-0 or averaged
  samples for fine signal). Highest-value lever: **@emit FORMAT HYGIENE** -- the 8B wraps poses in
  `*asterisk*` stage-directions, sometimes leaks a name prefix, and leaves unclosed quotes/parens;
  fix via a format instruction + a light output-cleanup strip (leading/trailing stray asterisk,
  name prefix). Strong cases (a clear spoken beat) already hit 4/5.
- **NEXT** -- Eval fidelity: filter omniscient-narrator paragraphs out of `scene_replay` input.
  The "omniscience" misses (Cricket reacting to a narrator's private exposition) are an EVAL-INPUT
  artifact -- wiki logs are edited prose with interior monologue the live bot's observable `@emit`
  stream would never contain. Optionally use the wiki page's character list for exact speaker
  attribution (so the do-not-puppet side of the eval is trustworthy too).
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
