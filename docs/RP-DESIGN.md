# RP context & scene-memory design (2026-06-21)

Design for the RP overhaul. Companion to `lore/RP-CHARTER.md` (the in-prompt rules) and
`docs/DESIGN.md`. Status: agreed; implementing in the build order at the bottom.

## Problem with today's RP path
`_handle_room` appends ONE `ContextLine` per socket line to `scene_queues[room]`, capped at
`SCENE_QUEUE_CAP = 60` lines and dropping the oldest (a known `TODO(memory)`). Multiline poses
become N entries with no notion of a "block." Retrieval pulls IC dossiers of present+mentioned
cast + self-history + the prior-scene summary; it does NOT pull the room description, Cricket's
past logs about the cast, or the wiki/T2 layer (OOC-only). Result: short, lossy scene memory and
thin grounding.

## Scene memory: byte-budgeted tail + append-only ledger
Replace the line cap with a two-tier per-room memory:
- **Verbatim tail** -- recent pose-blocks kept verbatim up to a BYTE budget
  (`inference.rp_context_bytes`, default ~6 KB). Before each generation, assemble the full
  prompt and, if over budget, trim the OLDEST blocks from the tail. Hard safeguard: the final
  assembled prompt stays under ~80% of `num_ctx`.
- **Append-only ledger** -- after each player pose-block, a distillation appends one entry:
  `<what happened> | Cricket's read: <his private reaction>`. Append-only, grows slowly,
  survives tail-trimming, so the arc stays grounded even after the verbatim head is dropped.
  On `!rp off` the ledger IS the scene summary persisted by the existing accretion loop
  (`save_scene_summary`). This RETIRES `SCENE_QUEUE_CAP`.

## Block grouping (multiline poses)
PennMUSH has no flag that bundles another player's multiline pose into one frame
(`OUTPUTPREFIX/SUFFIX` only frames our OWN command output). With `PARANOID`, every line is
prefixed `[Name(#dbref)]`. We group CONSECUTIVE same-(dbref) lines into one block, closing it
when the attributing object changes or after a short idle. (Newline subs: `%r` newline, `%t`
tab, `%b` space; `%n` is the enactor NAME, not whitespace.)

## Per-block distillation (one call, three outputs)
For each completed pose-block, an ASYNC call (main model, tiny output budget, off the reply's
critical path) returns:
1. ledger line ("what happened"),
2. Cricket's private read,
3. `{actors: [...], controlled_by: <dbref>}` -- which characters the block posed and who controls
   them.

## Ownership map -> do-not-puppet set (BOTH methods)
Per-scene map: character -> controlling dbref (many-to-one; one player poses self + kids + NPCs).
Built by BOTH:
- **Deterministic over-claim** (immediate, safe): the `PARANOID` dbref grounds the emitter; any
  non-Cricket named actor in the block is marked controlled-by-that-dbref. Over-claiming is safe
  for the guard.
- **Distillation-inferred** (precise): output (3) above refines actors/controller.
The union of characters controlled by non-Cricket dbrefs = the **do-not-puppet set**, injected
each RP turn as a hard block (react TO them, never pose their words/actions/outcomes). Cricket's
OWN newly-introduced NPCs are NOT in the set (he may run them; charter governs consequences).

## Dynamic cast + first-appearance prefetch
Retrieval re-runs each pose, so mid-scene arrivals are picked up automatically. Additionally, on
the FIRST appearance of a character this scene (new speaker, new posed subject, or a
connect/room-arrival), do a one-time richer lookup (dossier -> wiki/T2 if no dossier) and cache
it for the scene. Profiles grow with the cast.

## RP context sourcing (what goes in the prompt, and how)
| Source | Form |
|---|---|
| Players/characters present + mentioned | IC-facet dossiers, DISTILLED |
| Room description | probe `describe(loc(me))` like the room-name probe; VERBATIM-short |
| Cricket's past logs with this cast | `WikiIndex.logs_for_character` + prior-scene summaries, filtered to present cast; DISTILLED to relevant beats. Enable wiki/T2 in RP, IC-scoped. |
| This scene | verbatim tail (budgeted) + the ledger (distilled arc) |
| Do-not-puppet set | the ownership block |
| OOC nudges | the suggestion buffer (below) |
| Charter | `lore/RP-CHARTER.md`, injected on RP turns |

**Perfect memory = retrieval, not volume.** Canon Cricket remembers everything, but the context
window cannot hold everything and a dump drowns the live scene. Model it as RETRIEVAL: anything
relevant CAN surface (index + saved summaries, keyed to who is present), distilled to what matters
for THIS cast now, plus the verbatim recent tail. Perfect recall = perfect retrieval on demand.

## OOC -> RP suggestion bridge
Per-room suggestion buffer fed by the room-local `<OOC>` channel. A line referencing Cricket with
intent is captured `{from, text, favored?}` and injected as a "table talk" block: heed favorites
(Johanna/Atsvara/Bazil/ak), weigh/twist/resist the rest. (Needs production room-local OOC wiring.)

## Consent gate (serious harm to a player-character)
Per-room state machine. When a pose would do a SIGNIFICANT/MORTAL action to a PC:
1. Detect intent BEFORE posing (pre-pose intent check; the OOC nudge or the planned action).
2. Do NOT pose the setup. Emit an OOC request naming target + act, including the literal hints
   `!consent-ok` / `!consent-deny`. Set the room to PENDING-CONSENT.
3. BLOCK all pose generation for that room while pending.
4. The target player OR an admin runs `!consent-ok` (proceed: telegraph + act, never posing
   their outcome) or `!consent-deny` (drop it; pose something else).
NPCs need no consent, but the charter's "consequences are real / not invincible" rule applies.
Commands: `!consent-ok` / `!consent-deny` (admin + the addressed target).

## Build order
1. Block grouping (parser/router) -- prerequisite for distillation + ownership.
2. Scene ledger + byte-budget tail (retire `SCENE_QUEUE_CAP`); prompt-length safeguard.
3. RP charter injection + enable IC retrieval (room desc, past logs) in RP.
4. Ownership map (deterministic + distillation) + do-not-puppet block; first-appearance prefetch.
5. OOC -> RP suggestion bridge.
6. Consent gate state machine + `!consent-ok`/`!consent-deny`.
