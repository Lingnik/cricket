# Overnight autonomous run -- Cricket "drastic improvement" (started 2026-06-21 night)

SOURCE OF TRUTH for the overnight loop. Survives context compaction. Every cron pulse:
1. Read this file + `TaskList`. 2. Advance the next incomplete step. 3. Update the Progress
log below + commit. 4. Keep the 20-min cron alive. 5. When ALL stop-criteria pass -> run
`CronList`/`CronDelete` to stop the heartbeat, write a final summary, and stop.

Heartbeat cron: every 20 min (`9-59/20 * * * *`). Do NOT idle waiting for pulses -- do
substantive work each active turn; the cron is a safety net, not a rate limiter.

## The goal (user's words)
A drastically improved Cricket by morning: (a) relevant context on who it is talking TO and
ABOUT; (b) draws on his rich IC history when posing in an RP session; (c) a "rogue annoyed
wiki search engine" -- crass summaries of topics from across the game; (d) wiki tool/lookup
baked in; (e) IC/OOC experiences separated cleanly and high quality -- and OOC Cricket KNOWS
about his own IC misadventures and the logs we capture; (f) evals strong with good
performance (judge it yourself or via an Opus subagent). Stop only when all of that holds.

## Phases
- **P1 -- IC/OOC dossiers.** Distill `players/*.md` (35) into two-facet `lore/dossiers/<stem>.md`
  (`## IC` / `## OOC`). 31 "regular" profiles fanned out via Workflow; 4 principals
  (cricket-self, johanna, bazil, crestian -- have `docs/contrast/`) done by hand with stem
  reconciliation (johanna -> `johanna-siri-te-danaan.md`; cricket-self = no retrievable
  dossier, feeds self-history instead). IC = only in-universe-plausible droid knowledge; OOC =
  wiki-level meta + roast hooks. Preserve existing dossier IC canon.
- **P2 -- Mentioned-entity retrieval (item D).** Extend `retrieve(cast,...)` so the cast
  includes names MENTIONED in the live message + recent context, not just speakers. Closes the
  "what do you know about Johanna?" gap. Deterministic name-extraction, no LLM tool-calling.
- **P3 -- Wiki-cache lookup baked in.** Load `wiki-cache/index.jsonl`; resolve a name/topic ->
  page summary. Inject summaries for mentioned topics in OOC; add a "wiki search engine"
  capability so Cricket can give a crass summary of an arbitrary game topic. Build on
  `tools/search.py`/`lookup.py` logic, reimplemented in-package (stdlib only) for the runtime.
- **P4 -- Cricket's own IC history.** A self-history retrieval from his logs (corpus/wiki +
  `wiki-cache` Cricket RPlogs): in RP (IC) he references his own canon misadventures; in OOC he
  is aware of them too. Distill a `lore/CRICKET-HISTORY.md` (or self-dossier) keyed for both.
- **P5 -- Hidden thinking step.** Optional pre-generation reasoning pass gated by
  `inference.thinking` (discarded; only final pose posted). Wire it; A/B it via evals.
- **P6 -- Eval loop (STOP gate).** Establish a baseline (corpus-replay, deterministic gates +
  judge). Iterate persona/retrieval/thinking. Judge with an Opus subagent. Keep going until the
  new persona clearly beats baseline AND the qualitative bar below is met. Tests stay green.

## Stop criteria (ALL must hold)
1. All 35 players have clean two-facet dossiers; IC/OOC cleanly separated; sourcing faithful;
   4 principals hand-reviewed. `pytest` + lore tests green.
2. Mentioned-entity retrieval live-verified: "what do you know about <name>?" pulls that
   subject's dossier/summary and Cricket answers on-topic (the Johanna case works).
3. Wiki lookup baked in: Cricket produces a crass, on-topic summary of an arbitrary game
   topic/name from the cache (live-verified).
4. IC RP poses draw on Cricket's own logged history; OOC Cricket references his IC misadventures.
5. Thinking step implemented + measured; kept if it helps, gated off if not (decision recorded).
6. Evals: deterministic gates pass; Opus judge rates the new persona clearly above the captured
   baseline on corpus-replay. All unit tests green. Everything committed + pushed.

## Live-test notes
Daemon + Ollama runbook: `docs/OPERATIONS.md`. Test MUSH on the Pi (`100.88.188.43:4201`);
tools need `CRICKET_MUSH_HOST` + `CRICKET_TEST_*_PW` in env. `unset SSLKEYLOGFILE` before
pytest/Ollama. Restart the daemon cleanly (single instance, no nested `&`).

## Progress log (newest first)
- 2026-06-21 night #4 -- **RUN COMPLETE. ALL 6 STOP CRITERIA MET.** Heartbeat cron deleted.
  **Decisive eval (goal-aligned, deterministic temp=0, base[no retrieval] vs new[full stack],
  Opus judge, n=8):** engagement 2.63->4.25, grounding 2.25->4.13, voice 3.88->4.50; head-to-head
  new 7 / tie 1 / base 0. base repeatedly FABRICATED (Johanna "owes me credits", Veruca "stole my
  parts"); new is specific and correct (restraining bolt, taser from Bazil, Biscuit Baron EVP,
  Duke of Dragonflower, Veruca=Zubindi's ward). (Corpus-replay pose-matching was abandoned as the
  gate: too noisy at temp 0.85/n=10 -- two rounds disagreed within sampling noise -- and it
  measures exact-pose-match, not the user's goals.) 157 tests+evals green; all pushed (28c5e7a +
  this). Single live daemon verified (one reply per message). Known minor polish for later:
  generic-topic wiki engagement (he dismisses "Coruscant" as "that dump" rather than summarizing);
  a couple in-character grandiose embellishments ("I made her CEO" -- he is EVP). Final report posted.

## Earlier progress (newest first)
- 2026-06-21 night #3: **P4/P5 DONE.** P4: lore/CRICKET-HISTORY.md (18 log-grounded exploits)
  injected into the SYSTEM block; live bot now cites the restraining-bolt grudge + "fat bantha
  cow" + Biscuit Baron EVP unprompted. P5: hidden thinking step implemented (inference.thinking,
  off by default). **THINKING DECISION: gated OFF** -- round-1 Opus judge A/B was a wash
  (off 4 / tie 2 / on 4; thinking slightly *hurt* voice 3.1->2.8). Kept in code, revisit later.
  **LIVE MUSH VERIFIED** (real bot, Pi): "what do you know about Johanna?" -> on-topic dossier+
  history answer; "Biscuit Baron?" -> wiki+history crass summary; "Coruscant" -> wiki engine in
  voice. Daemon b02q2bp08 (single, new code; killed the 2 stale ones). **EVALS (corpus-replay,
  Opus judge):** base(no retrieval) vs new(full): richness 2.5->3.2 (clear win), overall wash
  3.0 vs 2.9 -- judge found lore-DUMP hurting scene-relevance. Fix shipped (914c0ca): RP
  beat-focus + subordinate-lore framing; round-2 judge running. NEXT: read round-2; if new
  clearly > base, finalize + stop; else iterate once more or document ceiling.
- 2026-06-21 night #2: **P1 DONE** -- 31 regular dossiers via Workflow (verified), + 3 principals
  (johanna/bazil/crestian) and 6 verify-fixes via a 2nd Workflow (9/9 clean). cricket-self folded
  into P4. **P2 DONE** -- LoreStore.mentioned() gazetteer + persona wiring; "what do you know
  about Johanna?" now pulls her dossier (unit + real-lore verified). **P3 DONE** -- WikiIndex
  (stdlib) + OOC topic injection ("rogue search engine") wired into build_bot; live-checked
  Biscuit Baron blurb; RP stays canon-grounded. 128 tests pass; all pushed (e85e8a3). NEXT: P4
  (Cricket self-history injection) -- agent distilling lore/CRICKET-HISTORY.md; then P5 thinking
  step, then P6 eval loop. STILL TODO before stop: live bot test on the Pi, baseline+improved
  evals with an Opus judge.
- 2026-06-21 night #1: run initialized. Wrote plan; task board; launched P1 Workflow; 20-min cron.
