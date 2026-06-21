# Persona affordances — handoff for the persona-building session

This is the contract the **program** (phase 1) exposes to the **persona** (phase 2). If you
are the agent building Cricket's persona: you should not need to touch networking, the MUSH
parser, or CUDA. You implement one protocol and author prompts/voice/memory policy.

See `DESIGN.md` for the whole system. This doc is the seam.

## Your deliverable is the active profile (plus lore content)

The persona is configuration and content, not new wiring — `LlmPersona` already reads the
active profile and assembles the model call. Your output is two things:

1. The **active persona profile** in the config DB (`data/cricket-config.sqlite3`) — a JSON
   doc with `identity`, per-location `directives`, an `inference` block (`backend`, `model`,
   `temperature`, `top_p`, `num_ctx`, `num_predict`, `stop`, `keep_alive`), and a `prompts`
   block:
   - `prompts.system` — the character sheet (the canonical copy lives in `lore/CRICKET.md`).
   - `prompts.fewshot` — a list of `{"user", "assistant"}` voice-anchor turns. These are
     injected as real conversation turns before the live turn, so the model *imitates*
     Cricket's specific voice rather than reading a description of it. This is the strongest
     lever on voice fidelity and register.
2. The **lore layer** in `lore/` — `CRICKET.md`, `voice-exemplars.md`, and per-character
   dossiers under `lore/dossiers/<kebab-name>.md`. A dossier may carry two facets delimited
   by `## IC` and `## OOC` headers; `LoreStore.retrieve(cast, scope)` returns the matching
   facet for the characters present (IC for room RP, OOC for channel chat), so Cricket stays
   canon-grounded in scenes but can draw on wider roast material on channels.

Edit the profile in the web UI (`GET /`) or via `PUT /api/profiles/{name}` then
`POST /api/profiles/{name}/activate`; `LlmPersona` reads the active profile live, so changes
apply with no restart.

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

## Inference backend

Generation runs against a **local Ollama server** over plain localhost HTTP -- the chosen
backend is `OllamaInferenceClient`, talking to the abliterated Llama 3.1 8B GGUF, which gives
Cricket a voice an aligned model refuses to produce. The client sits behind the
`InferenceClient` interface (`cricket/persona/inference.py`, alongside an `EchoInferenceClient`
stub for offline tests), so `LlmPersona` never imports model code and a different backend is
one class away.

You tune the backend through the profile's `inference` block -- model tag, `temperature`,
`stop` sequences, and `backend` (`"gpu"` or `"cpu"`, which maps to Ollama's `num_gpu`). The
measured backend spec -- the chat API, the GPU/CPU speed lever, and the prefix-cache
discipline plus cache-stable context layout you should preserve when shaping prompts -- is in
**`docs/INFERENCE_BACKEND.md`**.

## Smoke path before the model exists

Phase 1 ships `StubPersona` (echo/canned) and a harness so you can run the full bot against
a real or fake MUSH with no model, then swap in `LlmPersona`. Build and test your prompt
construction against recorded `Turn`s first; wire the live model last.
