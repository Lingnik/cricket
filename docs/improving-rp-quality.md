# Building Cricket v2: Improving Small-Model Roleplay Quality for a Star Wars Character Bot

## TL;DR
- **Abliteration is almost certainly NOT the main cause of your terse, instruction-dropping output.** Peer-reviewed evidence (Arditi et al., NeurIPS 2024) shows directional ablation of Llama-3 8B Instruct leaves capability benchmarks within the 99% confidence interval of baseline; the real problem is that you are using a *generic assistant-tuned instruct model* for a creative-RP task it was never built for. Switch to a purpose-built RP finetune.
- **Your single highest-leverage change is the model.** Drop abliterated Llama 3.1 8B Instruct and evaluate a dedicated uncensored RP finetune — top candidates are Mistral-Nemo-12B tunes (TheDrummer's Rocinante/UnslopNemo, MarinaraSpaghetti's NemoMix-Unleashed) if you can fit ~12B, or Llama-3 8B Sao10K Lunaris/Stheno v3.2 if you must stay at 8B. These are uncensored by training, so you keep no-refusal behavior without the "corporate assistant" prose.
- **Fix the prompt architecture before fine-tuning.** Match the model's native instruct template exactly, move character definition/format rules close to the generation point (low-depth injection, not buried at the top), strip few-shot examples the model parrots, and keep total context well under the model's limit. A LoRA is worth it only after these are exhausted — and your instinct to kill the planning pass is correct.

## Key Findings

1. **Abliteration's coherence cost is small and well-quantified — it is not your culprit.** For Llama-3 8B Instruct, directional ablation raised cross-entropy loss by only +0.014 on The Pile and +0.032 on Alpaca, with MMLU −0.8, ARC −0.1, GSM8K −1.6; Arditi et al. report that for MMLU, ARC, and GSM8K "orthogonalized models perform similarly to baseline models," with all metrics lying within the 99% confidence interval of baseline except Qwen 7B and Yi 34B. The exception is method-dependent: aggressive/optimization-based abliteration (e.g., Heretic) can damage math/reasoning heavily, and low-bit quantization can re-introduce refusals and quality loss.

2. **Generic instruct models write like "exhausted corporate assistants"; RP finetunes write like novelists.** The terseness and format-dropping you see is the signature of an assistant-tuned model doing creative RP, not of abliteration damage. Dedicated finetunes are trained on RP/story data without refusals, giving both uncensored behavior AND better prose.

3. **Matching the model's native instruct/chat template is the #1 mechanical fix.** The SillyTavern community's documented "Golden Rule" is to "Match CONTEXT TEMPLATE (Story String) and INSTRUCT TEMPLATE with your model." A mismatched template makes the model echo roles, repeat speaker tags, leak formatting, and degrade into loops.

4. **Prompt element *position* strongly affects small-model adherence.** Character definitions placed at the top of context have "weak active influence"; instructions placed closer to the generation point (low depth) are followed more reliably. This is the core lever for combating ignored lore and dropped format rules.

5. **Few-shot example dialogue is double-edged on small models.** Examples that overlap the model's training distribution are under-utilized, and small models frequently parrot/leak injected example text verbatim. SillyTavern provides targeted mitigations (example separators as stop strings, "Never include examples" when example text is already in the story string).

6. **Fine-tuning beats prompting for voice/format adherence — once prompt engineering is exhausted.** Empirical studies show LoRA fine-tuning substantially outperforms few-shot prompting for tone/format tasks, often with only 100–1,000 examples, but it is brittle to train/test prompt mismatch and only worth it after model+prompt fixes plateau.

7. **Your planning-pass instinct is right; two-stage pipelines help long-form coherence, not short turns.** Plan-then-write demonstrably helps *long* narratives but causes "over-determination" that is "counterproductive" for short creative output — exactly the verbatim-parroting failure you observed. For short round-robin poses, single-stage is better.

## Details

### 1. Abliteration, coherence, and whether to switch off it

**The empirical verdict: abliteration itself is cheap.** The foundational paper, *Refusal in Language Models Is Mediated by a Single Direction* (Arditi et al., NeurIPS 2024, arXiv:2406.11717), measured directional ablation (mathematically equivalent to weight-orthogonalization "abliteration") on Llama-3 8B Instruct directly. Cross-entropy loss rose only marginally: The Pile 2.348→2.362 (+0.014), Alpaca 1.912→1.944 (+0.032), on-distribution 0.195→0.213 (+0.018). Standard benchmarks barely moved: MMLU −0.8, ARC −0.1, Winogrande +0.4, GSM8K −1.6; only TruthfulQA dropped meaningfully (−3.4), which the authors attribute to fine-tuning/ablation away safety guardrails reducing TruthfulQA accuracy (consistent with Yang et al. 2023), not to general capability loss. They state plainly that "models maintain their coherence after undergoing weight orthogonalization," that for MMLU/ARC/GSM8K "orthogonalized models perform similarly to baseline models," and that all metrics lie within the 99% confidence interval of baseline except Qwen 7B and Yi 34B. A preliminary appendix experiment found ablation "does not change the model's chat personality or behavior outside of refusal."

**But method and quantization matter.** A 2025 cross-architecture comparison (*Comparative Analysis of LLM Abliteration Methods*, arXiv:2512.13655) found that for Llama-3.1-8B specifically, Heretic abliteration produced a KL divergence of just 0.056 — well under the paper's 0.1 "excellent preservation" threshold. However, the *aggressiveness* of the method drives damage: averaged across three benchmarked models, the single-pass tools were near-lossless on GSM8K (ErisForge −0.28 pp; DECCP −0.13 pp), whereas the optimization-based Heretic tool caused a "−18.81 pp; −26.5% relative" GSM8K collapse on Yi-1.5-9B (52.08% vs DECCP's 72.40%) — described as "an order of magnitude larger than the GSM8K standard error, indicating a substantial capability impact rather than sampling noise." The paper concludes "mathematical reasoning showed highest sensitivity to abliteration," and cautions its benchmarks "may not capture all forms of capability degradation (e.g., instruction-following quality, long-context coherence)." Separately, community reports note that low-bit quantization of uncensored models (e.g., the Q4 of Llama-3.1-8B-Lexi-Uncensored-V2) can re-introduce refusals and quality loss, with the author recommending Q8 or FP16.

**The real issue is "instruct model doing RP," not "abliterated model."** The honest read: your abliterated Llama 3.1 8B retains essentially all of base Llama 3.1 8B Instruct's capability. The terseness and instruction-dropping is what base Llama 3.1 8B Instruct *does* on open-ended creative RP — it is an assistant model that wants to be concise and "helpful." Practitioner consensus is that dedicated RP finetunes write markedly better prose than stock instruct models, which are described as writing "like exhausted corporate assistants." So abliteration is buying you uncensored output at near-zero capability cost — but it is *not* buying you good RP, because the underlying model isn't an RP model. Notably, Sao10K (creator of Stheno/Lunaris) reports that Llama-3.1-base tuning "did not give good results, unlike when I tested with Nemo base" — direct evidence that the Llama 3.1 lineage you're on is a weaker RP foundation than Mistral-Nemo.

**Better alternatives, ranked:**
- **Best:** A model that is *uncensored by training* (RP/ERP finetune) rather than abliterated after the fact. The community consistently finds fine-tuned-uncensored models more stable across diverse prompts than abliterated ones (this is also why Dolphin tunes dominate Ollama's uncensored download counts). You get no-refusal behavior AND RP-tuned prose in one model.
- **Acceptable:** A lightly-uncensored finetune like Llama-3.1-8B-Lexi-Uncensored-V2 (run at Q8/FP16), uncensored via fine-tuning rather than orthogonalization.
- **Avoid for v2:** Staying on generic abliterated Llama 3.1 8B Instruct — the worst of both worlds for RP (assistant prose + whatever minor abliteration cost exists).

### 2. RP-specific prompt frameworks and structure (SillyTavern-derived best practices)

Even if you don't use SillyTavern as your runtime, its community has solved most small-model RP prompt problems; adopt its architecture in your bot's prompt builder.

**Template matching (do this first).** SillyTavern's documented "Golden Rule": "Match CONTEXT TEMPLATE (Story String) and INSTRUCT TEMPLATE with your model" (Llama-3 tunes → Llama-3 Instruct template; Mistral-Nemo tunes → Mistral/Tekken as the tuner specifies). The official docs add that the instruct template "must match the expectations of an actual model... usually reflected in a model card on HuggingFace." A mismatched template is a leading cause of role-echoing, speaker-tag repetition, asterisk/format leakage, and degradation into loops. Modern backends (llama.cpp, KoboldCpp) can auto-derive the template from model metadata; verify the hash matches a known template. Since you serve via Ollama, confirm Ollama's chat template for your model matches the finetune's expected format exactly — Ollama defaults are a common silent source of this bug.

**Character definition format: prose wins for small models.** The community debate is between structured formats (W++, PList — bracketed key:value lists) and plain prose / Ali:Chat (trait expression through example dialogue). PList is token-efficient; plain prose and Ali:Chat tend to produce more natural in-character output. For an 8B model with strict format rules, a hybrid is the practitioner sweet spot: a compact PList for stable facts (species: astromech droid; demeanor: foul-mouthed) plus a few Ali:Chat-style lines showing Cricket's actual voice. Keep it short — every token in the character block competes with recent context.

**Position is everything (the core lever for your "ignores lore / drops format" problem).** SillyTavern documents that the character definition is pushed to the *top* of context, giving it "weak active influence" on the current turn ("If you make the Chat Context smaller, then you push the Character Context closer to your current conversation, which makes it stronger"). The fix used by experienced creators: put critical, must-obey instructions (format rules, current scene state, Cricket's voice reminder) in **depth-injected positions at low depth** (depth 0–1 is the bottom/most-recent part of the prompt, strongest influence; higher depth = weaker). Many creators keep the persona in a lorebook entry and put "[Genre; Tags; Scenario]" in the author's note at depth 1. **Recommendation for Cricket:** put your hard format rules (pose structure, asterisk conventions, round-robin turn discipline) as a depth-1 system injection right before the generation point, NOT only in the top-level system prompt. This single change typically fixes "drops the format rules after a few turns."

**Author's Note / depth injection** is the general-purpose tool for "meta-guidance" that must persist every turn (tone, format, length target). **World Info / lorebooks** inject lore only when keywords fire — ideal for Star Wars canon (locations, factions, droids) so you don't bloat every prompt with lore Cricket rarely needs. Keep WI entries concise and budget them (default 25% of context; raise only if needed). Note WI "helps guide... it does not guarantee" lore appears in output.

**"Post-history instructions" / jailbreak field** is SillyTavern's mechanism for placing instructions *after* the chat history (i.e., closest to generation), the strongest position for compliance. This is the right home for your most-violated rules.

**Combating specific small-model RP failures:**
- *Terseness:* longer/structured prompts that explicitly set a length target, editing short replies into the history as implicit examples, and a finetune that prefers longer outputs (most Nemo RP tunes do — users report needing to *cap* them).
- *Asterisk/format leakage* (e.g., trailing `**`, unclosed italics): SillyTavern users solve this with regex post-processing (trim incomplete sentences, remove stray `**`, fix unclosed markdown). Implement equivalent regex cleanup in your bot's output pipeline. Add example separators and persona names as stop strings to prevent impersonation and example-block leakage.
- *Parroting injected text / lore:* the documented few-shot failure — small models leak example dialogue verbatim. SillyTavern's own docs advise setting "Example Messages Behavior" to "Never include examples" when example text is already in the story string (to "avoid duplicating example messages"), and note the Example Separator stop-string is "Helpful if the model tends to hallucinate or leak whole blocks of example dialogue." Keep examples minimal and paraphrased rather than copy-pasted from logs.
- *Repetition/looping:* you're already on DRY; also confirm template match and keep context clean (no duplicated instructions/conflicting system prompts), since formatting issues cause more loops than sampler settings alone.
- *Breaking character:* keep a short voice anchor at low depth every turn rather than relying on the top-of-context persona.

**Context length before instruction-following degrades.** Two practical findings: (a) general guidance is to use only ~70–80% of the model's context window before accuracy drops; (b) RP-specific community reports document incoherence appearing above ~8K tokens on some 8B setups (often a RoPE-scaling/config artifact rather than a hard model limit). For an 8B/12B RP bot, treat ~8K–12K tokens as the practical reliable working window, summarize older history aggressively, and remember a smaller total prompt pushes your character/format instructions closer to the generation point — directly improving adherence.

### 3. Fine-tune vs. prompt for an 8B character bot

**The tradeoff.** Prompt engineering is fast, requires no training infra, and is the correct first move. But for a *single character with strict, stable format conventions*, fine-tuning has strong empirical support: studies on tone-of-voice and format adherence find LoRA fine-tuning reaches >90% target-format compliance with as few as ~100 training samples and outperforms few-shot prompting substantially (one identifier task showed a 4× exact-match improvement; tone-of-voice work showed fine-tuning converging by ~1,000 samples with no measurable quality loss / catastrophic forgetting). Crucially, fine-tuning bakes the format in so it survives long context and doesn't consume prompt tokens every turn — directly addressing your "drops instructions" problem.

**When it becomes worth it for Cricket:** after you have (a) switched to an RP-tuned base, (b) fixed template matching, and (c) optimized prompt position — if Cricket's *specific voice* (the foul-mouthed astromech cadence) and your *exact pose format* still aren't reliable. At that point a LoRA is the durable fix.

**Workflow:**
1. **Dataset from your existing RP logs.** Curate your best in-character Cricket poses (correct format and voice). Even 200–1,000 high-quality examples suffice. Format each as the *exact* prompt structure you'll use at inference (system + recent context → Cricket's pose).
2. **Critical: train and infer with the *same* prompt template.** LoRA is "highly sensitive to mismatches between train-time and test-time prompts"; a mismatch degrades performance. Lock your prompt format before training.
3. **QLoRA on the RP base model**, not on stock Llama. Typical settings from the literature: rank r=16–32, alpha 32–64, dropout ~0.1, 3 epochs, lr ~1e-4 to 2e-4 — trains in under an hour on a single A100-class GPU (or rentable cloud). Mask the prompt during loss so you only train on Cricket's output.
4. **Validate on held-out scenarios, not loss.** Low loss ≠ good poses; read actual outputs. Watch for overfitting (Cricket repeating canned lines) — a known small-data LoRA failure.
5. Keep the LoRA swappable; iterate the adapter without retraining the base.

**Existing RP base models to evaluate (ranked for your uncensored, strict-format, character-RP use case):**

*If you can run ~12B (recommended — better coherence/logical backbone at modest extra VRAM):*
- **TheDrummer Rocinante-12B-v1.1 / Rocinante-X-12B / UnslopNemo-12B** (Mistral-Nemo base): purpose-built for RP, uncensored, rich prose, good character adherence. Rocinante-X is praised as possibly the best sub-24B creative model with a solid "logical backbone" that "does not derail." Uses Mistral/Tekken template.
- **MarinaraSpaghetti NemoMix-Unleashed-12B** (Mistral-Nemo merge): repeatedly cited as a top 12B for RP — "takes character cards really well," smooth SFW/NSFW transitions, stable at min_p 0.1. Note users report it tends *long* (you'll cap length, the opposite of your current problem). Weakness: can forget complex world rules — mitigate with lorebooks.
- **Mistral-Nemo-12B-ArliAI-RPMax / Violet_Twilight-v0.2**: other well-regarded Nemo RP tunes worth A/B testing.
- Mistral Nemo also brings a 128K context window and the efficient Tekken tokenizer.

*If you must stay at 8B:*
- **Sao10K L3-8B-Stheno-v3.2** (Llama-3 base): the reference 8B RP finetune. Sao10K's v3.2 card highlights "Better prompt / instruction adherence" and "Better Multi-Turn Coherency" over v3.1, and mandates the Llama-3-Instruct template. (Sampling note: the widely-quoted "temp 1.4 + min_p 0.2" figure is from the *later* Llama-3.1-8B-Stheno-v3.4 card, not v3.2; third-party guides cite roughly temp 1.1–1.2 for v3.2. Tune empirically as you already do.)
- **Sao10K L3-8B-Lunaris-v1** (Llama-3 merge, Stheno's successor): balances creativity with logic/reasoning; the lowest-cost uncensored option on OpenRouter and heavily used. Model card recommends the Llama-3-Instruct template, temp 1.4, min_p 0.1.
- **Llama-3.1-8B-Lexi-Uncensored-V2** if you want to stay closest to your current Llama 3.1 lineage but uncensored-by-finetune rather than abliterated (run Q8/FP16).

**Base-model comparison summary:** At 7–8B, Llama-3 RP tunes (Stheno/Lunaris) are the strongest. Stepping to 12B Mistral-Nemo RP tunes (Rocinante/NemoMix-Unleashed) is the single biggest quality jump available in your size class and the option most likely to fix terseness, format adherence, and lore-following simultaneously — at the cost of a few extra GB of VRAM. The creator of the leading 8B tunes himself reports Nemo is a better RP base than Llama 3.1. All of these are uncensored by training, eliminating your need for abliteration entirely.

### 4. Planning pass and two-stage pipelines

Your empirical finding — that the planning pass is *actively harmful* because the model parrots the plan's verbatim lines — is consistent with the literature. Research on adaptive creative generation (UniCreative, arXiv:2604.05517) finds that rigid plan-then-write helps long-form narratives (macroscopic coherence) but on short, high-entropy tasks "suffers from over-determination... explicit planning is not only redundant but counterproductive," stifling the "stochastic spark" and "emotional resonance." For a round-robin pose (a short turn), planning adds latency and seeds parroting with no quality upside. **Kill it for short poses.**

Two-stage *draft-then-revise* pipelines do produce measurable gains in some settings (e.g., screenplay format conversion, long-form writing like LongWriter), and one community experiment showed program-optimization (DSPy/GEPA) lifting a tiny model's constrained-story quality — but these target *long, format-heavy* generation, not short conversational turns. The clear recommendation: for Cricket's short poses, use single-stage generation; reserve any two-stage approach for occasional long set-piece scenes if you ever need them. Note that small open models also fail two-stage pipelines outright at the format-parsing step (Llama-2 7B/13B showed 38–58% failure rates generating structured intermediate outputs), so multi-stage adds fragility at this scale.

## Recommendations

**Stage 1 — Model swap + template fix (do this week; highest ROI):**
1. **Replace abliterated Llama 3.1 8B with an RP finetune.** Primary pick: a Mistral-Nemo 12B RP tune (**Rocinante-12B-v1.1** or **NemoMix-Unleashed-12B**) if your hardware allows ~12B at Q4–Q6. 8B fallback: **L3-8B-Stheno-v3.2** or **Lunaris-v1**. Pull via Ollama or run GGUF in KoboldCpp.
2. **Match the instruct template exactly** to the finetune (Mistral/Tekken for Nemo tunes; Llama-3 Instruct for L3 tunes). Verify Ollama isn't silently applying a generic template. This alone often fixes leakage and looping.
3. Run at **Q6_K or Q8** if VRAM permits; avoid Q4 for uncensored tunes where refusals/quality can regress.

**Stage 2 — Prompt architecture (same week):**
4. **Move hard format/voice rules to a low-depth injection** (depth 0–1, after chat history / "post-history instructions" position), not just the top system prompt.
5. **Convert lore to a keyword-triggered lorebook**; keep the always-on character block short (hybrid PList + 2–3 Ali:Chat voice lines).
6. **Strip or paraphrase few-shot examples**; set "Never include examples" if example text is in the story string; add example separators + persona names as stop strings; add regex output cleanup for stray asterisks/unclosed markdown.
7. **Cap total prompt to ~70–80% of context (~8–12K tokens)**; summarize old turns so Cricket's instructions stay near the generation point.
8. **Remove the planning pass** for standard poses.

**Stage 3 — Fine-tune (only if Stage 1–2 plateau):**
9. Build a 200–1,000-example LoRA dataset from your best Cricket logs, formatted in the *exact* inference prompt template.
10. QLoRA on the chosen RP base (r=16–32, alpha 32–64, 3 epochs, lr 1e-4–2e-4), prompt masked. Validate by reading outputs, not loss.

**Benchmarks / thresholds that change the plan:**
- If the 12B tune is too slow for round-robin pacing (you want near-instant first token), drop to an 8B RP tune rather than reverting to abliterated stock.
- If a 12B RP tune still drops format rules after the position fix, that's your signal to fine-tune (Stage 3).
- If quantized uncensored tunes start refusing in-character profanity/edginess, move up a quant level (Q4→Q6→Q8) before considering abliteration.
- Track quality with a tiny private eval: a handful of fixed scene setups scored for (a) in-voice profanity/cadence, (b) correct pose format, (c) lore accuracy, (d) length. Re-run on every model/prompt change.

## Caveats
- **Llama 3.1 8B-specific abliteration benchmarks are partial.** The strongest capability-preservation numbers (Arditi et al.) are for the *original Llama-3 8B Instruct*, not 3.1; the 3.1-specific study (2512.13655) reports only KL divergence (0.056) for 3.1, not MMLU/GSM8K. Both nonetheless converge on "abliteration is near-lossless for Llama 8B-class models." Neither directly measures *creative-writing terseness*, which both papers explicitly list as outside their benchmarks.
- **RP model rankings are largely community/subjective.** Recommendations for Stheno, Lunaris, Rocinante, and NemoMix-Unleashed rest on practitioner consensus (Hugging Face discussions, OpenRouter usage, r/LocalLLaMA) and LLM-judged benchmarks (EQ-Bench), not rigorous controlled trials. Validate on *your* character and format with your own eval before committing.
- **EQ-Bench/creative-writing leaderboards use LLM judges** (Claude Sonnet) and are explicitly "a guide, not absolute truth"; they don't test conversational RP directly. Treat scores as directional.
- **Fine-tuning evidence is partly from adjacent domains** (tone-of-voice, customer support, code) rather than Star Wars character RP specifically; the direction (LoRA > prompting for format/voice, brittle to prompt mismatch) is robust, but exact sample counts for *your* voice will need iteration.
- **Hardware constraints not specified.** The 8B-vs-12B recommendation assumes you can spare a few extra GB of VRAM for 12B; if you're tightly VRAM-limited, the 8B RP tunes are the right call.
- Some cited figures come from vendor/community blog posts (MakeUseOf, Novita, MegaNova, Atlas Cloud) that may carry promotional bias; the core technical claims are corroborated by primary sources (arXiv papers, SillyTavern docs, Hugging Face model cards) where possible.