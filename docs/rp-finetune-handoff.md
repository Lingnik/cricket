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

## Next steps

1. Finish labeling (retry remainder until `_todo` empty), then validate the
   `_labeled/` maps (assemble + the deterministic checks) and hand titles/summaries
   to the wiki.
2. Eval the `lunaris-rp-12x-lora` epoch-1 checkpoint: base vs tuned on the
   held-out cantina scene (`finetune_eval.py`-style), check the `<pose char>`
   contract + impersonation vs the 130-sample smoke.
3. Rebuild `build_finetune.py` over the FULL labeled corpus (far beyond 29 logs)
   once labeling completes; reconcile profile slugs (a couple of alt-slug dupes
   like `liza-molokai`/`crestian-tarasar`).
4. Open: Blackwell/4-bit research (a prompt was drafted for deep research) to
   enable a 12B Rocinante/Nemo (128k) base — bf16 12B won't fit 24 GB training.
