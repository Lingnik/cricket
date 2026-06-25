# RP dataset + fine-tune pipeline — working handoff

State capture for an RP-LLM fine-tuning effort built on the SW1 MUSH wiki log
corpus. Written so work can resume after context compaction. Cricket is a
foul-mouthed astromech NPC; the broader goal is a **persona-conditioned** RP
poser that can voice any character given a profile, with Cricket as the headline.

## Goal & the core design decision

Fine-tune the local RP model (L3-8B-Lunaris, the `cricket` bot's base) so it
produces in-character MUSH poses. After debate we chose **conditioned, not
specialist**:

- **Conditioned (chosen):** each training sample's `system` block carries the
  *target character's* profile. Targets = poses by *any* character. The model
  learns "pose character X given X's profile + the scene." Generalizes to unseen
  characters (write a profile). The profile is a **required inference input** —
  removing it (a "stripped prompt") correctly yields a generic droid; that's the
  design, not a failure.
- **Specialist (rejected):** Cricket-only targets, no profile, bake him into the
  weights. Thin (~60 Cricket poses) and doesn't generalize.
- **Bare/dropout idea (rejected by user):** train the same pose with and without
  the sheet so the bare path also speaks Cricket. Sound technique (CFG-style
  conditioning dropout) but the user wants Cricket to *always* use the profile,
  so we don't risk the model under-reading the prompt.

Implication: **"lean prompt" means drop the scaffolding (RP charter, guards,
thinking pass, RAG), NOT the profile.** Train==serve must match byte-for-byte;
the runtime prompt is built in `cricket/persona/llm.py::_build_messages`.

## The three datasets

1. **`data/dataset/`** — Cricket-specific. 14 logs where Cricket is in-scene
   (of 36 that mention him; 22 reference-only are in `_rejected/`). Per-block
   attribution. `cricket_embedded.jsonl` = 20 Cricket poses *carved* out of
   other characters' blocks (he's narrated inside Johanna's poses in old logs).
   `_verdicts.json` = QUALIFY/PRESENT_MINOR/REFERENCE per log. ~40 native + 20
   carved Cricket poses — the hard ceiling on Cricket-voice data.
2. **`data/dataset2/`** — 29-log candidate set (14 Cricket + 15 era-stratified
   breadth), the **validated per-line** format. `name_map.csv` (variant→player),
   `names_1_exact/2_close/3_nomatch.csv` (DB matching, with the user's
   `bazil_added` annotations in #3), `NAMES.md` (resolution policy).
3. **`data/dataset_full/`** — the FULL 1,220-log corpus run (in progress).
   `_labeled/<name>.json` = `{name,title,summary,rows:[{line,type,actor,b}]}`
   per log (title+summary also feed Crestian's wiki). `_profiles/<slug>.md` =
   40 generated character sheets. `_render/` = line-numbered inputs (gitignored,
   regenerable). `_loglist.json` / `_todo.json` drive the labeling fan-out.

## Pipeline & tools (all in `tools/`)

- **`rplog_to_jsonl.py`** — deterministic parser. `parse_page` → meta rows +
  blank-line block segmentation + `%t`/`%r` MUSH encoding. `--render` emits
  ONLY non-blank body lines prefixed with raw line numbers (the labeler copies
  the number — no counting/skipping). `body_line_span`, `is_blank` (treats
  `<br>`/`&nbsp;`-only lines as blank).
- **Per-line attribution** — an LLM labels each non-blank line `{line, type, actor}`
  (type ∈ pose/scene/room/desc/ooc/system). Line numbers are the structural
  authority, NOT whitespace (fixes blocks that fuse two characters). Protocol in
  `tools/ATTRIBUTION_PROTOCOL.md`.
- **`pose_xml.py`** — THE shared module (train + serve must both use it).
  `render_scene`/`render_row` → `<pose char="X">…</pose>` / `<narration>` /
  `<ooc>` transcripts. `render_target` wraps the assistant label. `SYSTEM_RULE`
  = the output contract. `parse_generation(raw, expected_char)` → (text, verdict
  ok|puppet|recovered|empty); a second character's `<pose>` tag = parse-detected
  puppeting → cut + flag (replaces the old regex `_clean_output` heuristics).
- **`rplog_assemble.py`** — map + source → final JSONL; validators: full line
  coverage, round-trip fidelity, contiguous seqs.
- **`build_finetune.py`** — builds chat samples. `profile_for(actor)` resolves
  Cricket→`CRICKET.md`, else actor→handle (via `name_map`)→`_profiles/<slug>.md`,
  else no-profile. Windows the transcript to fit; `main()` targets ALL poses
  across `data/dataset2/*.jsonl` at `INPUT_BUDGET=2100` → `data/finetune/train.jsonl`.
- **`finetune_qlora.py`** — bf16 LoRA (r16) on L3-8B-Lunaris, prompt-MASKED
  (loss only on the pose), Llama-3 chat template. `MAXLEN=2560`, `OUT=lunaris-rp-12x-lora`.
  Base snapshot path in `data/finetune/base_path.txt`.
- **`finetune_eval.py`** — base vs tuned on a prompt, runs output through the
  puppet parser.
- **`dataset_index.py`**, **`carve_cricket.py`**, plus throwaway `_batch2_*`.

## Name resolution (MUSH DB)

DB dumps at `knowledge/sources/mush-dump/` (gitignored — PII + re-fetchable):
`enum.dump` (every dbref `#n FLAGS name`), `enum-players.dump` (1,391 players),
`finger.{jsonl,csv}` (per-player bio: full_name, alias, background, lastconnected).
Key facts: **players are single-token first names** (Johanna Siri te Danaan →
player `Johanna`); **Cricket is a Thing/puppet (`#8720 TOXnp`), not a player**;
~45% of posing weight is by **purged** historical players the live DB can't
resolve (user hand-annotated those in `names_3_nomatch.csv:bazil_added`). The
flags parser must accept non-letter flag chars (e.g. `~`) and skip
`#-1 NO SUCH OBJECT` lines. finger `full_name` resolves cross-name aliases
(`Lorn Rhys` → player `Malus`). **Sonnet labels were rejected** (less accurate);
Opus only.

## Current job status (at handoff)

- **Labeling `w688xsvxu`** — full corpus, Opus, **15 concurrency** (size 50),
  ~479/1220 done, idempotent (skip-guard + `_todo`). Relaunch the remainder each
  pass until complete: stop → recompute `_todo` → relaunch (size = remaining/concurrency).
- **12× training `bafej3v8y`** — local GPU, 1,584 samples (29 logs, all poses),
  2 epochs, ~47 s/step (~5 h), per-epoch checkpoints. Adapter → `lunaris-rp-12x-lora`.
- **Profiles** — 40/40 done. Smoke artifacts preserved: `train_smoke.jsonl`,
  adapter `lunaris-cricket-xml-lora`.

## Hard-won tips / gotchas

- **Opus brownout:** "Server is temporarily limiting requests (not your usage
  limit)" — server-side, Opus-specific (Sonnet sailed through during it).
  **1 concurrency reliably clears a brownout**; ramp up (6, then 15) as it eases.
- **Workflow `args` arrive as a STRING** — every script must
  `typeof args === 'string' ? JSON.parse(args) : args`. Silent default-fallback
  bug otherwise (forced size 5 / ~14 concurrency, which tripped the throttle).
- **Per-workflow agent cap is 1000**; concurrency cap is ~min(16, cores-2). To
  run BELOW the concurrency cap, use FEWER/BIGGER batches (≤N batches → ≤N
  concurrent). Idempotent file-writing + a skip-guard make any pass resumable.
- **Don't run two big fan-outs at once** — the combined burst trips the rate
  limit. Serialize.
- **For index-into-array fan-outs, agents miscount** — give each agent its OWN
  single-target file (e.g. `_ptargets/<slug>.json`) instead of "use index i".
- **Windows VRAM:** bf16 8B LoRA fits 24 GB at `MAXLEN=2560`; `4096` pushed VRAM
  to 98% → WDDM spill to shared RAM → ~150 s/step (vs 33). Keep seq short.
- **transformers 5.x:** `apply_chat_template(..., return_tensors="pt")` returns a
  BatchEncoding — use `enc["input_ids"]`.
- **Cache windows / pacing:** see ScheduleWakeup guidance; sub-5-min polls stay
  cache-warm.

## Audit outcome (full-corpus labels)

A "Full" audit was run on the 1,220 labeled logs:

- **Structural (deterministic, gating):** the assembler enforces full line coverage,
  round-trip text fidelity, contiguous seqs. After fixes, **1220/1220 pass.** Fixes:
  (a) `rplog_assemble.is_noise` now treats pure divider/rule lines (`----`, `____`,
  `====`, `* * *`) as non-content -- not required for coverage, dropped from output,
  never a round-trip obligation (resolved phantom-line + most uncovered-line fails
  without re-labeling, no regressions); (b) two targeted re-label passes fixed 42
  then 12 logs whose real defect was dropped hard-wrapped-prose continuation lines
  (`_relabel.json`, `_relabel2.json`).
- **Smell triage (heuristic):** 26 zero-pose logs (all `talk_`/redirect/system
  dumps -- correctly non-pose) and 21 no-actor poses (unnamed-NPC poses, e.g. "The
  nurse...") were both **false alarms** -- labeler discrimination is clean.
- **Semantic (independent Opus judge, 30-log stratified sample, `_judge_report.json`):**
  2,602 lines judged -> **~3.0% type / 0.8% actor disagreement; 22/30 logs flawless.**
  The one systematic weakness: **narrative third-person poses (no `Name ` prefix)
  sometimes typed `scene`** -- an undercount (~2,800 lines across ~477 logs by the
  `scene`-row-with-dialogue heuristic, an upper bound). A pose mislabeled `scene` is
  *lost as a training target but not corrupted* (remaining 70k poses are correctly
  attributed); it hurts wiki attribution more than training.
- **DECISION (user): train as-is.** Accept 97% line-accuracy; NO pose-as-scene
  re-label. Known limitation recorded here. (Cheap wins left on the table if ever
  revisited: 53 `<Location - Name>`-tagged poses across 5 logs with actor in the tag;
  the actor-swap logs the judge flagged, e.g. `Meeting_with_Petra_and_Davyd`.)

Corpus now: `data/dataset_full/_assembled/<name>.jsonl` (1,220 turn-level logs, same
schema as `data/dataset2`, gitignored -- regenerable from `_labeled` + pages via the
assembler). 70,586 attributed poses.

## Next steps

1. DONE: labeling (1220/1220) + full audit (train-as-is at 97%). Titles/summaries
   in `_labeled/<name>.json` are ready to hand to the wiki.
2. Eval the `lunaris-rp-12x-lora` adapter once the 12x run (`bafej3v8y`) finishes
   and frees the GPU (eval during training OOMs at 24 GB): base vs tuned on a
   held-out scene, check `<pose char>` contract + impersonation vs the smoke.
   `checkpoint-198` = epoch 1, preserved for an epoch-1-vs-epoch-2 compare.
3. DONE/RUNNING: full-corpus training. `tools/build_finetune_full.py` walks all
   1,220 `_assembled` logs (74,259 poses / 1,573 actors), synthesizes meta (title from
   `_labeled`, `present` cast from pose actors), and applies a BALANCING CURRICULUM --
   raw 74k is ~100h/epoch AND imbalanced (Jessalyn 4,315 ... Cricket only 52). Caps:
   profiled actors 120 each, tail 10 each, Cricket upweighted to the profiled cap.
   At 120/10 = 18,271 samples (8,019 profiled). Trainer is now env-configurable:
   `TRAIN_FILE` / `OUT_DIR` / `EPOCHS` / `SAVE_STRATEGY` / `SAVE_STEPS`. Launched as
   `TRAIN_FILE=train_full.jsonl OUT_DIR=...lunaris-rp-full-lora EPOCHS=1
   SAVE_STRATEGY=steps SAVE_STEPS=400` (~2,283 steps, ~27h, checkpoints every 400).
   Eval the result the same way as the 12x (set `ADAPTER=...lunaris-rp-full-lora`).
4. Open: Blackwell/4-bit research (a prompt was drafted for deep research) to
   enable a 12B Rocinante/Nemo (128k) base — bf16 12B won't fit 24 GB training.
