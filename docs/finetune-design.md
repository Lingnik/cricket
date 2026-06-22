# Cricket Fine-Tune Design (QLoRA adapter for the RP persona)

Status: design only. No training code, no runtime changes. This scopes a QLoRA
fine-tune of the chosen RP base model so Cricket's specific voice (foul-mouthed,
scheming astromech) and the exact `@emit` pose format survive long context without
spending prompt tokens every turn. It is the "Stage 3" lever from
`docs/improving-rp-quality.md`: pursue it only after the model swap (Stage 1) and
prompt-architecture fixes (Stage 2) plateau. This document does not reorder those
stages; it specifies what Stage 3 is, so the corpus generator (running now) emits
rows that fit it.

The single most-cited failure mode in the research doc governs every section below:
**train and infer must use an identical prompt format and the base model's native
instruct template.** LoRA is "highly sensitive to mismatches between train-time and
test-time prompts." Everything here is built to reproduce, byte-for-byte, the prompt
`cricket/persona/llm.py` builds at runtime.

---

## 0. What the runtime prompt actually is (the target to reproduce)

The completion we train on is a single Cricket pose. The prompt that must precede it
is exactly what `LlmPersona._build_messages` assembles for an RP turn. Reading
`llm.py` closely, that is a chat-message list:

1. **One `system` message**, concatenated in this fixed order:
   - `prompts.system` (the persona/character sheet from the active profile; the
     committed source is `knowledge/runtime/lore/CRICKET.md`, synced via
     `tools/wire_persona.py`),
   - `## Your own past exploits (real, yours -- draw on them and brag):` +
     `self_history` (from `LoreStore.self_history()`, i.e. `CRICKET-HISTORY.md`),
   - `## RP rules (these OUTRANK your own desires):` + `rp_charter`
     (`LoreStore.rp_charter()`, i.e. `RP-CHARTER.md`) -- RP turns only,
   - `turn.directives` if present,
   - the three standing guards appended verbatim: `_NO_FABRICATION`, `_RECOUNT_RULE`,
     `_NOVELTY_RULE`.

2. **Optional few-shot turns** (`prompts.fewshot`): alternating `user`/`assistant`
   pairs. See the template-lock note below -- these are part of the prompt and must
   be present (or absent) identically at train and infer time.

3. **One live `user` message**, joined by blank lines from these parts in order:
   - the memories block, headed in RP by `Background you may draw on ONLY if it fits
     this exact moment (do NOT recite or info-dump it; react to the scene):` followed
     by the retrieved dossiers / shared-history / do-not-puppet / first-appearance
     blocks (the full output of `_retrieve_memories`),
   - `Recent conversation (oldest first):` + the scene history, one line per
     `ContextLine` rendered as `"%s: %s" % (speaker, _to_mush_markup(text))`,
   - `The most recent beat to react to:` + the quoted, MUSH-markup'd last beat
     (trimmed to 300 chars),
   - the register/length instruction (`Match the scene's length and register. ...`)
     whose wording is chosen by the average byte-length of the other characters'
     last four poses (three bands: snappy / full paragraph / 2-3 paragraphs),
   - the RP compose instruction (`Compose Cricket's next pose: ... raw SW1 @emit ...
     separate paragraphs with %r%r%t ...`).

The completion is the `assistant` message: Cricket's pose, in MUSH markup (`%r`/`%t`),
with no name prefix, no asterisks, balanced quotes -- the same shape `_clean_output`
expects to receive raw and lightly repair.

**Single-pass only.** The hidden planning pass was removed (`inference.thinking=false`,
confirmed by the `ab_thinking` decision rule adopting arm B). Do **not** build
two-stage (plan->write) training examples. There is no `Your private plan (use it...)`
part in the target prompt. Train the model to go straight from scene context to pose.

---

## 1. JSONL turn-row schema (feedback to the corpus generator)

The corpus is one JSONL file per RP log, one row per turn (a single character's
pose/say/emit). Cricket's turns are the fine-tuning **targets**; everyone else's turns
are **context** used to reconstruct the scene-so-far for those targets. To build the
exact prompt above from rows, each row needs the fields below. The driving principle:
a row must carry everything the runtime would have known at the moment that turn was
posed, so a historical turn can be replayed through the same prompt builder.

| Field | Type | Why it is needed for training-example construction |
|---|---|---|
| `log_id` | string | Stable id of the source log (filename stem). Scene-so-far windows never cross logs; held-out splits are taken per log (Section 5). |
| `turn_index` | int | 0-based position of this turn within its log. Defines ordering and the exact prefix of context for any Cricket target (all turns with a lower index in the same log). |
| `speaker` | string | The display/pose name as it appears in the scene (e.g. `Atsvara`, `Cricket`). Becomes the `"<speaker>: <text>"` line in `Recent conversation`, and feeds gazetteer cast resolution for dossier retrieval. |
| `speaker_dbref` | string or null | Stable per-character id (`#dbref` style, or a synthetic stable token if the log lacks one). The do-not-puppet builder in `_retrieve_memories` keys ownership off `ContextLine.dbref`; a row with no dbref is treated as narration. Required to reproduce that block faithfully. Narration rows carry null. |
| `is_cricket` | bool | Marks the target rows. True only when Cricket is the **acting subject** (his own pose/speech), matching `evals/replay.py:is_cricket_pose` semantics -- not paragraphs that merely mention him. The completion side of every training example is an `is_cricket: true` row. |
| `kind` | string | One of `say` / `pose` / `emit`, mirroring `ContextLine.kind` and `SpeechKind`. Determines line rendering and, for the target, the `Response.action`. RP targets are `emit`/`pose`. |
| `text` | string | The verbatim turn text **with the player's original `%r`/`%t` MUSH markup preserved** (or the literal newlines/tabs that map to them -- see Section 6). This is the raw material both for context lines (passed through `_to_mush_markup`) and for the completion. Do not pre-strip markup; normalization is a pipeline decision, not a corpus one. |
| `location` | string | Scene/room id or name. Becomes `turn.location`; also the unit the runtime would probe for room description. Lets the pipeline group turns into scenes and reconstruct `current_room_desc`. |
| `location_kind` | string | `room` (RP) or `channel` (OOC). RP targets are `room`; the charter and IC-facet dossiers inject only for RP. Channel turns, if any, would build the OOC-facet prompt instead -- keep them tagged so they are excluded from the RP fine-tune (Section 6). |
| `timestamp` | string or null | ISO timestamp if the log carries one (wiki logs have `last_edit_ts`, not per-turn times). Secondary ordering key and provenance; `turn_index` is the primary order. Null when unknown. |
| `cast_present` | list of strings | Best-effort list of characters present/named at this turn (display names). Optional but valuable: it lets the pipeline reconstruct dossier retrieval without re-running the gazetteer, and it is the ground truth for the do-not-puppet set. If omitted, the pipeline derives it from prior `speaker` values + `LoreStore.mentioned` (the same path the runtime uses). |
| `source_offset` | int or null | Character/paragraph offset into the source log for the turn, for traceability and dedup. Optional. |

Notes for the generator:

- **One concern per field.** Keep `speaker` as the pose name and resolve to canonical
  lore names downstream (the runtime does this in `_retrieve_memories` via
  `LoreStore.mentioned`). Do not pre-canonicalize, so the pipeline can reproduce the
  runtime's exact resolution.
- **Narration is a first-class row** with `speaker: "scene"` (matching
  `scene_replay.attribute`) and `speaker_dbref: null`. The opening room-description
  paragraphs of a log should be emitted as `scene` rows so the pipeline can rebuild
  `current_room_desc` from `speaker == "scene"` rows, exactly as `replay()` does.
- **`is_cricket` is the contract surface for targets.** The generator should apply the
  same acting-subject test as `evals/replay.py:is_cricket_pose` (lead-subject, or
  speaker-after-quote) so targets are Cricket *posing*, never Cricket being *mentioned*.

---

## 2. Dataset construction pipeline (rows -> training examples)

Each training example is `(messages, completion)` where `messages` is the exact
inference prompt for a historical Cricket turn and `completion` is that turn's pose.
The pipeline reuses the live prompt builder rather than re-implementing it, which is
the only way to guarantee the template lock (Section 2.4).

### 2.1 Target selection and scene-so-far reconstruction

For each log, walk rows in `turn_index` order. For every `is_cricket: true` row T:

- **Context** = all rows in the same `log_id` with `turn_index < T.turn_index`,
  rendered into `Turn.context` as `ContextLine(speaker, dbref, kind, text)` in
  oldest->newest order. Cricket's own earlier turns are included (the runtime feeds
  the bot's past replies back into history).
- Build a `Turn` with `mode="rp"`, `location`, `location_kind="room"`,
  `bot_identity=BotIdentity("Cricket", "#3")`, `text=""` (RP poses compose from the
  scene, not a single line), and `context` as above.
- Run that `Turn` through the **live** `LlmPersona._build_messages` (with the live
  `_retrieve_memories`, lore store, wiki index, vector index wired exactly as
  `evals/scene_replay.py:_build_persona` does) to get `messages`.
- The `completion` is `T.text`, normalized to MUSH markup the same way the runtime
  renders context (Section 6) and **trained as-is** -- i.e. with `%r%r%t` paragraph
  breaks, no name prefix, no asterisks. Apply the *idempotent* parts of
  `_clean_output` to the reference (strip a leaked name prefix, balance quotes) so the
  label matches what a well-behaved model should emit; do **not** strip markup the
  model is supposed to produce.

This is the same machinery `evals/scene_replay.py` already exercises (block grouping ->
per-block ledger -> dossiers/shared-history/do-not-puppet -> `_build_messages`). The
training-set builder is, in effect, `scene_replay.replay()` stopped one step early:
it captures the assembled `messages` instead of calling the model, and pairs them with
the real reference pose at the cut.

### 2.2 Scene-context window / byte budget

Match the runtime budget exactly. RP context is byte-budgeted, not line-capped:
`inference.rp_context_bytes` (default ~6 KB; see `docs/RP-DESIGN.md`). When the
assembled prompt exceeds budget, the runtime trims the **oldest** verbatim pose-blocks
from the tail while keeping the append-only ledger. The training builder must apply the
identical trim: assemble the full prompt for turn T, and if over `rp_context_bytes`,
drop oldest blocks from the verbatim tail (the ledger entry for a dropped block
survives, exactly as at runtime). The hard safeguard also carries over: the final
assembled prompt stays under ~80% of `num_ctx` (the research doc's ~70-80% context
guidance). Because the builder calls the same code path, this is automatic if the
builder runs the live trim logic rather than reimplementing it.

### 2.3 Reconstructing dossier / lore retrieval for a historical turn

At runtime `_retrieve_memories` is *live*: it pulls IC-facet dossiers for present and
mentioned cast, Cricket's shared history with that cast, the do-not-puppet ownership
block, first-appearance wiki prefetch, and (OOC only) wiki/vector topics. For a
historical turn this must be reconstructed against the **same lore store state** the
adapter will face at inference:

- Run `_retrieve_memories` on the reconstructed `Turn`, with `LoreStore`,
  `WikiIndex`, and `VectorIndex` pointed at `knowledge/runtime/lore` and
  `knowledge/runtime/wiki` (as `scene_replay` does). The cast is derived from the
  context `speaker`s + `LoreStore.mentioned` over the line texts, exactly as the
  runtime does -- so the same dossiers fire.
- This means the **lore store is a fixed input to the training set**. Pin the lore /
  wiki snapshot used to build the dataset and record its identity in the dataset
  manifest. If the lore store changes materially after training, the injected
  memories block shifts and the adapter sees a prompt distribution it was not trained
  on -- a soft version of the template-lock failure. (Open question in Section 7.)
- A subtle caveat: a present-day dossier may contain facts that postdate an old log.
  This is acceptable and even desirable -- the adapter must perform well against the
  dossiers it will actually be fed at inference, which are today's dossiers. We are
  not reconstructing the historical knowledge state; we are reconstructing the
  *runtime prompt* for that scene's beats. Keep this explicit in the manifest.

### 2.4 Template lock (the load-bearing requirement)

Two layers must match between training and inference:

1. **The chat-message content** (Section 0): identical system concatenation, identical
   few-shot block (present or absent the same way), identical user-message part
   ordering and wording, including the register-band instruction and the RP compose
   instruction. The only correct way to guarantee this is to **generate training
   prompts by calling the live `_build_messages`** rather than templating by hand.
2. **The base model's native instruct template**: the chat messages must be rendered
   to a token string using the *exact* template the chosen RP finetune expects
   (Section 3), via that model's tokenizer `apply_chat_template` (or the finetuner's
   documented template). Do not invent a template. The research doc's "Golden Rule":
   match the context/instruct template to the model; a mismatch causes role-echoing,
   tag repetition, asterisk/format leakage, and loops.

At inference the bot serves through Ollama with a Modelfile that pins the template
(today `cricket-abliterated` re-creates the canonical Llama-3.1 template, per
`docs/OPERATIONS.md`). The training renderer must produce **the same** token sequence
that this Ollama template produces for the same messages. Verification step before any
training run: take a handful of assembled `messages`, render them (a) through the
training tokenizer's chat template and (b) through the Ollama Modelfile template for
the target model, and diff the resulting strings. They must be identical up to the
assistant turn. Lock this before spending a single training step.

### 2.5 Prompt masking

Train the loss on **Cricket's output tokens only**. Mask (label = -100) every token of
the system message, few-shot turns, and the live user message; unmask only the
assistant completion (the pose) and its terminating turn tokens. This is the research
doc's explicit instruction ("Mask the prompt during loss so you only train on
Cricket's output") and prevents the adapter from learning to reproduce the injected
dossiers/instructions. With the chat-template renderer, derive the mask from the
assistant-turn token span (most instruct templates delimit it cleanly).

---

## 3. Base model

Align with the in-flight model eval: **L3-8B-Lunaris-v1 (Llama-3 8B merge) vs
TheDrummer Rocinante-12B-v1.1 (Mistral-Nemo base)**. The fine-tune targets whichever
that eval selects; this section records the template constraint each choice imposes,
because the base model dictates the second layer of the template lock.

- **L3-8B-Lunaris-v1** -- uses the **Llama-3 Instruct** template. Lowest-cost
  uncensored option, balances creativity with logic; the 8B fallback in the research
  doc. If chosen, the training renderer and the Ollama Modelfile must both emit the
  Llama-3 Instruct template (`<|start_header_id|>...<|end_header_id|>` /
  `<|eot_id|>`), which is also the dialect today's `cricket-abliterated` Modelfile
  pins -- so the existing serving template is reusable.
- **Rocinante-12B-v1.1** -- Mistral-Nemo base, uses the **Mistral / Tekken**
  template. The research doc's primary pick if hardware allows ~12B: better coherence,
  richer prose, "logical backbone" that does not derail, and Nemo is reported by the
  8B tunes' own author as a better RP base than Llama 3.1. If chosen, both the training
  renderer and a **new** Ollama Modelfile must emit the Mistral/Tekken template; the
  current Llama-3.1 Modelfile cannot be reused.

Constraint summary: the model choice is not template-neutral. Whichever wins, the
QLoRA must be trained on that model's native template and served on a matching
Modelfile. Do not train on one dialect and serve on another. (Picking between the two
is the model eval's job, not this design's -- recorded as an open question.)

---

## 4. QLoRA configuration

Values are taken directly from the research doc's Stage 3 / Workflow section and kept
intact. Rationale follows each.

| Hyperparameter | Value | Rationale (from `docs/improving-rp-quality.md`) |
|---|---|---|
| Quantization | 4-bit base (QLoRA), adapter in higher precision | "QLoRA on the RP base model" -- fit the base in 4-bit, train a small adapter; keeps the base swappable and the adapter cheap to iterate. |
| Rank `r` | 16-32 | Research doc: "rank r=16-32". Start at the low end (16) for a single-character, single-format target on a small corpus to limit adapter capacity; raise toward 32 only if voice/format adherence underfits. |
| Alpha | 32-64 | Research doc: "alpha 32-64". Pair with rank (alpha ~= 2x rank is the doc's implied ratio: r16/a32 or r32/a64). |
| Dropout | ~0.1 | Research doc: "dropout ~0.1". Regularizes against the known small-data LoRA failure (memorizing/repeating canned lines). |
| Epochs | 3 | Research doc: "3 epochs". With only hundreds of examples, more epochs risk the canned-line overfit; fewer may underfit the voice. Validate by reading outputs at each epoch checkpoint, not by loss. |
| Learning rate | 1e-4 to 2e-4 | Research doc: "lr ~1e-4 to 2e-4". Standard QLoRA range for this scale. |
| Prompt masking | on (Cricket output tokens only) | Research doc: "Mask the prompt during loss so you only train on Cricket's output." See Section 2.5. |
| Target modules | attention (and MLP) projections per the base | Follow the finetuner's standard QLoRA target set for the chosen architecture; not over-specified in the research doc. |
| Corpus size | ~200-1,000 high-quality examples | Research doc: LoRA reaches >90% format compliance with as few as ~100 examples; "Even 200-1,000 high-quality examples suffice." Curate for quality over volume (Section 6). |

Keep the adapter swappable so it can be iterated without retraining the base, per the
research doc ("Keep the LoRA swappable; iterate the adapter without retraining the
base"). Serving: load the merged or adapter-applied weights into a new Ollama model tag
alongside `cricket-abliterated`, with the template-matched Modelfile (Section 3).

---

## 5. Validation plan

Judge the adapter by **reading outputs, not loss** (research doc: "Low loss != good
poses; read actual outputs"). The existing eval harnesses provide the reading surface;
reuse them rather than building new ones.

- **Held-out scenes.** Split by `log_id`, not by individual turn, so no scene leaks
  across the train/eval boundary. Reserve a set of logs (candidates from
  `evals/scene_replay.py:DEFAULT_REPORT_LOGS` -- Charity Ball, Droid Control, Ghastly
  Gala, Birthday Baroness, Bespin Blows Up, Ballistic Equipment Parts) for evaluation
  and exclude every Cricket turn in them from training. The corpus is recent-Cricket
  weighted via the existing `min_year` filter in `evals/replay.py` (the present-day
  unhinged persona, not the competent-2000s one); apply the same filter to targets.

- **Scene replay (qualitative read).** Run `python -m evals.scene_replay --report
  <out.json>` against the adapter-served model on the held-out logs to produce
  generated-vs-reference pairs for the Opus judge, scored for in-voice profanity/
  cadence, pose format, lore accuracy, and length (the research doc's four-axis private
  eval). Use `--samples > 1` (temp 0.85) to measure the live voice distribution, and a
  deterministic (temp 0, seed 0) run as the reproducible regression baseline -- both
  modes are already built in.

- **Mechanical panel (regression gate).** Run `evals/ab_thinking.py` and
  `evals/ab_sampling.py` to get the countable-defect panel (voice marker rate,
  asterisk leak, name presence, length median/min, latency). Re-purpose the A/B
  structure as **base-model vs adapter** arms: build the persona once with the stock RP
  model and once with the adapter applied, run the same scenes x samples through
  `_generated_pose`, and compare distributions. The `parrot` metric is structurally 0
  now (no plan), so the live signals are voice, asterisk, length, and names. Pre-
  register the decision rule before running (as `ab_thinking` already does) so judge/
  sampler noise cannot move the goalposts.

- **Overfit / canned-line watch (known small-data LoRA failure).** Specifically check
  for the adapter repeating stock catchphrases verbatim (the exact thing `_NOVELTY_RULE`
  fights in the prompt). Two concrete checks: (a) measure n-gram overlap between
  generated poses and the training references -- a spike vs the base model signals
  memorization; (b) scan generations for the known leaked catchphrases (e.g. the
  "FUCK THE POLICE" non-sequitur called out in `llm.py`) appearing out of context.
  If canned-line repetition appears, reduce epochs, lower rank, or raise dropout, and
  re-curate the corpus for diversity (Section 6). Track these across epoch checkpoints,
  because the failure emerges with over-training.

---

## 6. Data hygiene

The corpus is hundreds of turns, but only the best in-voice Cricket poses should become
targets. Curation, normalization, and pollution-exclusion all matter more than raw
count at this scale.

- **Curate best-in-voice targets.** Prefer recent-era Cricket (the `min_year` filter)
  and poses that already exhibit the target shape: a self-describing third-person
  `@emit` opening, at least one crude spoken line in quotes, correct `%r%r%t` paragraph
  breaks, balanced quotes, no asterisks, no name prefix. Drop poses that are
  out-of-voice (the competent-droid early era), pure narration with no spoken line, or
  malformed. Hand-rank toward the doc's ~200-1,000 high-quality band rather than
  including every Cricket turn.

- **Normalize `%r`/`%t` MUSH markup consistently with the runtime.** The runtime shows
  the model context via `_to_mush_markup`: it replaces literal `\r\n`/`\n` with `%r`
  and `\t` with `%t`. Apply the **same** transform when rendering context lines in the
  training prompt, and ensure the **completion** is in the same notation the model is
  asked to emit (the compose instruction explicitly says "separate paragraphs with
  `%r%r%t`"). The wiki logs store paragraph breaks as `<br>` / blank lines and indents
  as the `&nbsp;` runs that `evals/replay.py:strip_markup` collapses; the corpus
  generator must decide a single canonical mapping from source-log markup to the
  literal newlines/tabs that `_to_mush_markup` will convert -- and the pipeline must
  apply `_to_mush_markup` identically to context and target. Inconsistent markup
  between context and completion teaches the model the wrong output notation.

- **Dedup.** Remove near-duplicate poses (same scene re-uploaded, repeated boilerplate
  openings) by normalized-text hashing and high n-gram-overlap clustering; keep one
  representative per cluster. Duplicates inflate the canned-line overfit risk.

- **Exclude test pollution.** Drop anything that originated from the bot's own test
  runs or scene-harness probes rather than authored human RP: the corpus must be
  *human-authored Cricket*, not the current model's own outputs (training on model
  outputs would bake in present defects). The runtime keeps test traces under
  `data/traces*/` and masks test probes from memory; ensure none of that material
  enters the corpus. Also exclude OOC/channel turns (`location_kind == "channel"`) from
  the RP fine-tune -- they build a different (OOC-facet) prompt and target a different
  register.

- **Held-out isolation.** Hygiene and splitting interact: do the `log_id` held-out
  split (Section 5) *before* dedup so a near-duplicate of a held-out pose cannot sneak
  into the training set.

---

## 7. Open questions / decisions for a human

1. **Base model + size: Lunaris-8B vs Rocinante-12B.** This is owned by the in-flight
   model eval, but it gates the fine-tune's template (Llama-3 Instruct vs
   Mistral/Tekken) and the serving Modelfile. The fine-tune cannot start until the eval
   selects one, because the training template must match it. Decision needed: which
   base does the adapter target, and is the hardware budget for 12B at an acceptable
   serving quant (Q6/Q8) confirmed?

2. **Lore-store snapshot pinning.** The injected memories block is reconstructed
   against a *live* lore/wiki store, so the training prompts depend on a specific
   snapshot of `knowledge/runtime/{lore,wiki}`. Decision needed: pin and record the
   snapshot used for training, and define a policy for retraining (or accepting drift)
   when dossiers change materially after the adapter ships.

3. **Few-shot in the locked prompt.** The runtime prompt may include `prompts.fewshot`
   voice-anchor turns. Because they are part of the template lock, they must be present
   or absent identically at train and infer time. Decision needed: does the fine-tuned
   adapter keep the few-shot block (and if so, frozen at which exact examples), or does
   the fine-tune replace the few-shot's job and the block is removed from both training
   prompts and the live profile together? The research doc leans toward stripping
   few-shot once the voice is baked in, but that change must be made on both sides at
   once.

4. **Corpus size / curation depth.** The research doc's ~200-1,000 band spans a wide
   range; the actual count depends on how many recent in-voice Cricket poses survive
   curation and dedup. Decision needed: a target count and how aggressively to hand-rank
   versus filter heuristically -- this trades coverage of his range against the
   canned-line overfit risk.
