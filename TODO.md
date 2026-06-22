# Cricket -- open work

Status: **NEXT** (in progress) / **SOON** / **LATER** / **DEFERRED** / **DONE**. See
`STATUS.md` for the plain-language summary and `docs/OPERATIONS.md` for the runbook.
The 2026-06-21 overnight "knowledge upgrade" run is logged in `docs/overnight-run.md`.

## Resume context (2026-06-21, post-infrastructure session)
Everything on `origin/main` (secrets-clean). The bot runs end-to-end on the Pi test MUSH over
**WebSocket + oob JSON** (trusted attribution; telnet is the fallback), under a **supervisor**
(`cricket supervise --persona llm --verbose`) the user runs interactively. Restart the worker to
load new code via the OOB socket `4251` `{"cmd":"restart"}` or the `restart` control command on
`4250`. Live **activity stream** on `4252`; `cricket ctl --tail --raw` is the split REPL.
**One memory DB, no swapping** -- clean test data via mask/purge (Memory + Audit web tabs, console
`mem`/`audit`, `/api/memory|events`). RP quality: voice/format/grounding fixes done, reasoning ON,
distillation fixed. Eval: `evals/scene_replay.py` (deterministic temp-0 for format/fit/puppet;
`--samples N` temp-0.85 for voice) + `evals/goals.py`. See OPERATIONS.md for the full runbook and
the project memory for the architecture summary. Deps now: `websockets`, `prompt_toolkit`.

## Remaining -- next up (post-infrastructure)
- **LEFT INTENTIONALLY (per user, for troubleshooting):** the greedy `@listen me=*` relays
  connect/disconnect notices over oob -> they're filtered for behavior but still logged to the
  audit trail + streamed (clutter, not harmful). Verbose logging kept available on purpose. If it
  becomes noise: scope the listener / filter `_CHANNEL_NOTICE` kinds out of the audit log + stream.
- **NEXT (RP quality):** with the grounding fix in (present cast dossiers now inject), re-measure
  fit/voice in a fresh traced scene; the remaining lever is voice consistency at temp-0.85 (bimodal
  -- best-of-3 hits 4/5). Eval-fidelity: exact-cast attribution from each log's `{{Rplog|chars}}`.
- **LATER:** production go-live (real `<Cricket>`/`<OOC>` channels + real creds); hands-on CRUD tuning.

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

## Done (2026-06-21, batch 4 -- reorg + format hygiene)
- **DONE** -- Lore colocated under `knowledge/{runtime,sources}` (see OPERATIONS.md "Knowledge
  layout"); daemon now `_root`-relative (no CWD dependency). 179 tests + live smoke test green.
- **DONE** -- `@emit` FORMAT HYGIENE: `_clean_output()` in `persona/llm.py` (drop leaked
  'Cricket says,' prefix, strip `*asterisk*` stage-directions, unnest channel-say quotes, balance
  dangling/unclosed quotes) + tighter RP/chat instructions. Report regen: asterisks 12->0,
  name-prefixes ->0, unbalanced quotes 3->0. Live chat smoke test confirms clean output.

## Remaining -- next up
- **STABLE BASELINE (2026-06-21, deterministic temp-0, judge5):** voice 2.33 / fit 2.83 /
  quality 2.33; plausible 6/12; FORMAT CLEAN on all 12; 0 puppet leaks. Format hygiene + do-not-
  puppet CONFIRMED working. This report is reproducible (greedy), so future tuning is measurable
  against it. METHODOLOGY NOTE: temp-0 greedy biases AGAINST the crass low-probability voice, so
  the 2.33 voice is a LOWER BOUND -- live (0.85) smoke tests are genuinely crass. Use temp-0 for
  FORMAT/FIT/PUPPET regression; measure VOICE live or via averaged 0.85 samples.
- **DONE (voice consistency).** Live-voice measure (`--samples 3`, temp-0.85, Opus voice judge)
  proved voice is NOT weak: best-of-3 = 4.0, no scene that can't reach a strong voice. The misses
  were almost all VOICELESS action-only poses (his wit lives in dialogue). Added an RP instruction
  to land a spoken crude line + prefer crass over literary -> voiceless samples 12->0 of 36, live
  voice mean 2.86 -> 3.44. Live smoke test clean + crass.
- **DONE (voice micro-lever).** Dropped the "FUCK THE POLICE" example from CRICKET.md (it anchored
  the tic) + added "vary your profanity to the moment"; re-wired. Live 36-sample regen: tic 5-6 -> 2,
  voiceless still 0.
- **DONE (bug).** Bare bang-commands ("!rp on") on a chat channel are now dispatched from authorized
  admins, not ranted at (router.py); was the OOC `!rp on` -> rant bug. Verified live (rp_enabled
  [] -> ['#0'], control reply not a rant).
- **ADDRESSED (fit) -- grounding + beat-focus.** Two changes: extended `_NO_FABRICATION` to the
  live scene (no inventing who/what is present) and anchored the pose on the SINGLE most-recent line
  (not a stale earlier beat). DIMINISHING RETURNS / not cleanly measurable: a single temp-0
  generation judged by a non-deterministic Opus judge carries ~0.3 judge-noise, so fit score deltas
  this small are noise -- the qualitative judge notes (unanimous "ignores the most-recent beat")
  drove the change, not the number. Further fit gains need either averaged-judge measurement or a
  smarter context (less competing earlier context in the prompt). Lower priority now.
- **LOW PRIORITY** -- Eval fidelity via ATTRIBUTION (the deterministic judge already shows 0 puppet
  leaks, so the main value left is masquerade costume-alias resolution -- niche). CORRECTION (evidence in
  corpus/wiki/2025-03 - Charity Ball.txt + Droid Control): the wiki logs are RAW `@emit` pose
  streams, NOT GM-rewritten narrative. The earlier "filter omniscient narration" plan was based on
  a wrong premise -- what looked like a narrator's private exposition is just players posing their
  OWN character's interiority + the NPCs they control + scene-setting `@emit`s, ALL of which the
  live bot does see in the room stream. So do NOT filter it. The real, narrower issues: (a) the bot
  should not METAGAME -- react to/act on another PC's posed-but-IC-private interiority (an RP-charter
  skill, legitimately present in the stream); (b) focus on the actionable beat over ambient setting.
  The valid harness fix is exact-cast ATTRIBUTION from each log's `{{Rplog|characters=...}}` manifest
  (top of file), which also resolves costume aliases / one-player-posing-many-NPCs that the gazetteer
  heuristic mis-splits. No new Cricket log needed -- these are typical SW1 logs.
- **LATER** -- Hands-on persona tuning via the new CRUD panel (now pleasant; not yet used in
  anger for a real tuning pass).
- **DONE** -- Web UI now surfaces the harass-on-connect toggle (POST `/api/harass` + a control-panel
  switch beside Mute; verified live). The thinking flag was ALREADY in the Inference editor.

## Remaining -- blocked on you / deferred
- **LATER** -- Production go-live: reconfigure to the real `<Cricket>` + room-local `<OOC>`
  channels; point `.env` at the real MUSH (needs real creds).

## Closed (won't do)
- **CLOSED** -- "Clean-mode" safety gate: permanently dropped by product decision -- Cricket is
  fully unhinged on every channel, by design.
- **CLOSED** -- Speaker name-match tightening: not a real problem. Almost every player runs a
  single character (name == character); genuine ambiguity is rare common names like "Tyler",
  which the dossier gazetteer + retrieval already resolve to the right one (e.g. Tyler Damion).
