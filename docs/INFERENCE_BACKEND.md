# Inference backend -- Ollama (abliterated Llama 3.1 8B)

The persona's text generation runs against a **local Ollama server** over plain
localhost HTTP. No TLS, so none of this machine's OpenSSL/Applink issues apply, and the
client needs no third-party HTTP library (stdlib `urllib` is enough).

All numbers below are **measured on the 5090 laptop** (24 GB VRAM, 61.6 GB RAM), not
estimated. GPU vs CPU differ only in **speed, never quality**.

## Model
- Ollama tag: `hf.co/mlabonne/Meta-Llama-3.1-8B-Instruct-abliterated-GGUF:Q5_K_M`
- Already pulled/registered (`ollama list` to confirm). 5.7 GB on disk.
- Abliterated Llama 3.1 8B -- refusal direction removed, so it stays in character for
  crass/edgy roles the stock model sanitizes.

## API -- the chat endpoint
`POST http://127.0.0.1:11434/api/chat`, `Content-Type: application/json`:

```
{
  "model": "hf.co/mlabonne/Meta-Llama-3.1-8B-Instruct-abliterated-GGUF:Q5_K_M",
  "messages": [
    {"role": "system", "content": "<RP rules + character bio>"},
    {"role": "user",   "content": "<memories + RP scene log + 'your turn' instruction>"}
  ],
  "stream": false,
  "keep_alive": "30m",
  "options": {
    "num_ctx": 16384,
    "num_predict": 400,
    "temperature": 0.85,
    "top_p": 0.95,
    "stop": ["\n\n\n"]
  }
}
```

Use the chat endpoint (not `/api/generate`) so role separation and the prompt template
are handled for us. The response carries timing fields in **nanoseconds**:
`prompt_eval_count`, `prompt_eval_duration`, `eval_count`, `eval_duration` -- log these
for real per-turn rates (tok/s = count / (duration / 1e9)).

## Backend selection -- one option field
The GPU/CPU lever is `options.num_gpu`. This is what the profile's `inference.backend`
selector maps to:

| Backend            | options                | Effect |
|--------------------|------------------------|--------|
| GPU (default)      | omit `num_gpu`         | Ollama auto-loads all layers it can onto the 5090 |
| CPU only           | `"num_gpu": 0`         | all layers on CPU/RAM, GPU untouched |
| Partial (future)   | `"num_gpu": N`         | N layers to GPU, rest to RAM (for an 11 GB 2080Ti desktop) |

Confirm placement with `ollama ps` -> the PROCESSOR column shows `100% GPU`, `100% CPU`,
or a split.

**`num_ctx` and `num_gpu` must stay constant across calls in a session** -- changing
either forces a model reload and dumps the warm cache. Pick once per session.

## Measured performance (5090 laptop)

|                                    | GPU                          | CPU          |
|------------------------------------|------------------------------|--------------|
| Generation (per-turn cost)         | 48-80 tok/s                  | 7-9 tok/s    |
| One ~400-token pose (3 paragraphs) | ~5-8 s                       | ~40-60 s     |
| Cold prompt eval (context)         | ~900-1300 tok/s              | ~32 tok/s    |
| Cold eval of 16K-token context     | ~15 s                        | ~8 min       |
| Cold eval of 32K-token context     | ~30 s                        | ~17 min      |
| Footprint @ 32K ctx                | 10 GB VRAM                   | ~7 GB RAM    |
| Footprint @ full 128K ctx          | 22 GB VRAM (fits, 100% GPU)  | ~22 GB RAM   |

- **Max context window: 131,072 tokens on BOTH** -- a model limit (shared input+output),
  not hardware. Reserve ~512 for output -> ~130K usable input. Do not exceed 128K.
- **GPU**: holds the full window fast -- best for real-time, snappy back-and-forth, or
  large context.
- **CPU**: effectively unlimited memory headroom but compute-bound; weakness is **cold
  prompt eval**, not capacity or generation. Use it to keep the GPU free and when ~40-60 s
  poses are acceptable (fine for asynchronous MUSH play).

## The critical optimization -- prefix caching (both backends)
Verified: an unchanged prefix dropped prompt-eval from **82.9 s to 1.3 s (~64x)**. While
the model stays loaded (`keep_alive`), Ollama keeps the kv-cache and **only re-evaluates
tokens past the longest matching prefix**.

So expensive context processing is a **one-time cost, not per-turn**. Steady state per
turn ~= (eval of only the new player poses since last turn) + (generating our pose),
**roughly constant regardless of total context size** once warm. **Output length is the
dominant per-turn lever** -- shorter poses = linearly faster turns. Keep the cache warm
with a long `keep_alive` (`"30m"` or `-1`).

## Context layout -- design for cache stability
Order **most-stable first**; append new content **only at the end**:

```
[system: RP rules + character bio]   <- never changes     -> cached all session
[memories block]                     <- changes rarely     -> invalidates from here when edited
[RP history, oldest -> newest]       <- append-only at end -> only new tail re-evaluated
[current "your turn" instruction]    <- the tail
```

Rules (these bind the persona prompt-assembly in phase 2):
- **Append, never insert/edit earlier.** Any earlier change invalidates the cache from
  that point on.
- **Truncation is the expensive event.** Dropping the oldest turns shifts the prefix and
  costs a near-full cold re-eval. Avoid it by **summarizing old turns into the memories
  block** periodically rather than letting raw history grow unbounded.
- Run in an **8K-32K working window**, not 128K -- keeps cold/re-eval in the
  seconds-to-low-minutes range and dodges "lost in the middle" quality loss. The 128K
  ceiling is safety margin so we rarely truncate, not a target to fill.

## Recommended defaults
- `temperature` 0.8-0.9, `top_p` 0.95 for lively RP (lower = more repetitive/safe).
- `num_predict` ~300-400 for a few paragraphs; lower to speed up CPU turns.
- `num_ctx` 16384 to start (bio + memories + a healthy rolling log).
- `stop` sequences to cut poses cleanly (the model occasionally trails on an open quote):
  the next speaker's name prefix, or `"\n\n\n"`.
- `keep_alive: "30m"` (or `-1`) to hold the warm cache between turns.

## Optional server-level tuning (Ollama service env, not per-request)
- `OLLAMA_FLASH_ATTENTION=1` -- faster attention, lower memory.
- `OLLAMA_KV_CACHE_TYPE=q8_0` -- halves kv-cache (64 KB/token vs 128). Irrelevant for the
  5090 (already fits at 128K), but it is what makes the **2080Ti desktop** viable at large
  context later. Slight, usually negligible quality cost.

Set these in the environment before the server starts; they apply to all requests and do
not change the per-call API.

## Gotchas
- The PyTorch->integrated-GPU misroute on this machine is a transformers/uv-venv problem
  ONLY. Ollama is unaffected (Go server, own CUDA path; `ollama ps` confirms the 5090).
- Do not run a heavy GPU job (e.g. the old FP16 transformers path) concurrently with
  GPU-mode Ollama -- they compete for 24 GB and one will OOM or silently fall back to CPU.
- `num_ctx`/`num_gpu` changes mid-session trigger a reload and discard the warm cache.

## How this maps to the bot
- `persona/inference.py` gains an `OllamaInferenceClient` (stdlib `urllib`, POST to the
  chat endpoint) implementing the existing `InferenceClient` interface. The `EchoInferenceClient`
  stub stays for tests/offline.
- The profile `inference` block carries: `backend` (`"gpu"`|`"cpu"` -> num_gpu omit/0),
  `num_ctx`, `num_predict`, `temperature`, `top_p`, `stop`, `keep_alive`, `model`.
- `LlmPersona` (phase 2 owns prompt content) assembles messages per the cache-stable
  layout above and calls the client; it logs the response timing fields per turn.
