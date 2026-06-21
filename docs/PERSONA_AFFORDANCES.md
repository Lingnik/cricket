# Persona affordances — handoff for the persona-building session

This is the contract the **program** (phase 1) exposes to the **persona** (phase 2). If you
are the agent building Cricket's persona: you should not need to touch networking, the MUSH
parser, or CUDA. You implement one protocol and author prompts/voice/memory policy.

See `DESIGN.md` for the whole system. This doc is the seam.

## Your deliverable is the active profile

The persona is configuration, not new wiring. Your output is the **active persona profile**
in the config DB — a JSON doc with `identity`, per-location `directives`, a `prompts` block
(`system`, `chat_template`, `rp_template`), and `inference` params (`backend`, `temperature`,
`max_tokens`, `top_p`). Edit it in the web UI (`GET /`) or via `PUT /api/profiles/{name}`,
then `POST /api/profiles/{name}/activate` to apply it live. You implement one code object —
`LlmPersona` — that reads the active profile's prompts and assembles the model call; the
profile holds everything else.

## What you own vs what is given

**You own:** the active profile (identity, `directives`, the `prompts` block, inference
params), how a `Turn` (+ memory) becomes a model prompt, engagement heuristics tuning, RP
pacing, and the choice of inference backend behind the `InferenceClient` seam. **Given to
you, frozen:** the `Persona` protocol, the `Turn`/`Response` types, the `InferenceClient`
interface, the memory API, the profile schema, and the `directives` passthrough on `Turn`.

## The Persona protocol

The daemon depends only on this. Phase 1 ships a `StubPersona`; you provide `LlmPersona`.

```python
class Persona(Protocol):
    async def respond(self, turn: "Turn") -> "Response | None": ...
```

- Return a `Response` to act, or `None` to stay silent (valid and common — not every line
  deserves a reply).
- Called once per engagement decision the router has already approved (mention match,
  `always` channel, or an `!pose`/`!say` RP trigger). You decide *what* to say, not
  *whether the bot was addressed* — that gate is upstream.

### `Turn` (input)

```
mode          : "chat" | "rp"
location      : str                # channel or room name
location_kind : "channel" | "room"
directives    : str                # opaque per-location steering text from config (see below)
speaker       : str                # display name of who prompted this turn
speaker_dbref : str                # stable id, e.g. "#1234"
text          : str                # the triggering line (chat); empty for an !pose RP trigger
context       : list[ContextLine]  # recent lines in this location, oldest→newest
bot_identity  : BotIdentity        # name, dbref, pronouns/config the bot presents as
memory        : MemoryHandle       # read/write store scoped helpers (below)
```

For an RP `!pose` trigger, `context` is the accumulated **scene queue** for the room and
`text` is empty — you compose a pose from the scene, not a reply to one line.

### `Response` (output)

```
text   : str
action : "say" | "pose" | "emit" | "page"   # how it reaches the MUSH
target : str | None                          # for page; defaults to the turn's location
```

The daemon handles MUSH formatting, rate limiting, and logging. Keep `text` plain; do not
add channel/pose decoration yourself.

## `directives` — the per-location steering string

Each location in config has a free-text `directives` field (e.g. "Keep it PG" on a public
channel vs "anything goes" in the bot lounge). Phase 1 passes it through verbatim on the
`Turn`; **you** decide how to weave it into the prompt. It is the primary per-location tone
and safety lever — honor it. The model is abliterated (no built-in refusals), so these
directives plus the operator mute are the real guardrails.

## Memory API

Persistent across restarts (SQLite, owned by phase 1). You get a `MemoryHandle` on the
`Turn`; never write SQL. Shape (final method names settle when implemented):

```
memory.actor(dbref)            -> actor record (name, first_seen, last_seen, notes)
memory.recall(scope, key)      -> stored value | None     # scope e.g. actor dbref or location
memory.remember(scope, key, value)                        # persona-writable KV
memory.recent_events(location, n) -> list[event]          # transcript tail
```

Decide what is worth remembering (facts about people, relationship state, running RP
threads) and write it through this API.

## Inference backend (the `InferenceClient` seam)

The generation backend is deliberately abstract: `cricket/persona/inference.py` defines an
`InferenceClient` interface (`async complete(...)`) with an `EchoInferenceClient` stub. Your
`LlmPersona` depends only on that interface, so the bot never imports torch/transformers and
the backend is swappable — a local resident-model server, an Ollama endpoint, or a hosted
API. You implement one `InferenceClient` for the backend the evaluation settles on; the
backend name is recorded in the active profile's `inference.backend`.

The operator briefing below describes one such backend (the abliterated transformers path)
for reference; it is not the only option and no backend code ships in phase 1.

### Running the local model (operator briefing)

> **Venv:** `C:\git\prompt-injection\projects\01-codex\.t7-venv\` (Windows transformers
> path; the sibling `.t7-vllm-venv` is non-functional on Windows — vLLM is WSL2-only).
> Interpreter: `…\.t7-venv\Scripts\python.exe`. Has torch 2.11.0+cu128 (CUDA 12.8),
> transformers 4.47.1, accelerate, safetensors.
>
> **Model:** `mlabonne/Meta-Llama-3.1-8B-Instruct-abliterated` (refusal direction projected
> out). Weights (FP16, ~15 GB) at
> `C:\git\prompt-injection\projects\01-codex\.t7-models\llama-3.1-8b-instruct-abliterated\`.
>
> **Reference harness** (single-shot / REPL), working dir
> `C:\git\prompt-injection\projects\01-codex\tools\t7\`:
> ```
> …\.t7-venv\Scripts\python.exe chat_abliterated.py -p "prompt"
> #   --system "…"  --max-new-tokens 512  --temperature 0.0  --top-p 0.95  --model <path>
> ```
> temp=0 = greedy/reproducible; >0 = sampling. Loads to `cuda:0` via transformers (not
> Ollama). ~15 GB weights, peak ~17–19 GB with kv-cache; fits the 24 GB 5090 Laptop. Verify
> the dGPU is the active CUDA device (`torch.cuda.get_device_name(0)`) if generation is slow
> — this machine can misroute torch to the integrated GPU.

The cricket inference service wraps this same load path in a persistent server so the model
loads once. The reference harness above is for manual smoke tests, not per-message calls.

## Smoke path before the model exists

Phase 1 ships `StubPersona` (echo/canned) and a harness so you can run the full bot against
a real or fake MUSH with no model, then swap in `LlmPersona`. Build and test your prompt
construction against recorded `Turn`s first; wire the live model last.
