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
- 2026-06-21 night: run initialized. Wrote this plan; created task board; launched P1 dossier
  Workflow (31 regular profiles, generate+verify); created 20-min heartbeat cron. NEXT: hand-do
  the 4 principals + start P2 (mentioned-entity retrieval) while the Workflow runs.
