# RPlog -> turn-dataset: attribution protocol

You are converting ONE cached SW1 MUSH wiki RP log into a finished JSONL
turn-dataset. The mechanical parse is already done for you. Your job is the
*interpretive* half: say who posed each block, classify non-pose content, and
judge whether **Cricket** is actually a character in the scene.

## Inputs you are given
- **Raw log**: `knowledge/runtime/wiki/pages/<NAME>.txt` — the source of truth.
- **Pre-parse**: `data/dataset/_preparse/<NAME>.jsonl` — one row per metadata
  field and one row per body block, already cleaned and encoded:
  - indentation -> literal `%t`, internal line breaks -> literal `%r`.
  - `meta` rows (with `key`) are done; keep them verbatim unless the parser
    visibly truncated a value (cross-check the raw and fix if so).
  - body rows arrive as `{"type":"pose","actor":null,"text":...}` placeholders.

## What a "turn" is
This is freeform narrative RP: each blank-line-separated block is **one player's
post** (one turn). A post usually leads with a little scene-setting then delivers
its character's action/speech. Keep the pre-parse's block boundaries 1:1 — do
**not** merge or drop blocks. Only split a block into two rows if it plainly
contains two *different* characters' separate poses (rare); preserve the text
exactly when you do.

## For each body row, set `type` and `actor`
- `type:"pose"` — the block delivers one character's action or speech.
  Set `actor` to that character's **canonical full name** (see roster below).
  Opening scene-setting inside an otherwise-actioned pose stays part of that pose.
- `type:"scene"` — pure environmental/establishing narration or a room
  description with no acting character. `actor:null`.
- `type:"desc"` — an in-scene description of a character, droid, or object
  (e.g. a "look" / pose intro describing someone's appearance). `actor:null`
  unless one character is clearly delivering it, in which case name them.
- `type:"ooc"` — out-of-character chatter, headers, footers, credits. `actor:null`.

### Actor naming
Use one canonical full name per character for the whole file (e.g.
`Johanna Siri te Danaan`, `Lynae Cassius`, `Kracen Ecks`, `Galen Rourke`,
`Cricket`, `Atsvara Tarasar`). Resolve nicknames/titles to the canonical name.
NPCs voiced in passing (a guard, a bartender) get their in-fiction label
(e.g. `Devaronian officer`). The roster from the `characters` meta row is a
hint, but trust the body — characters often act without being listed (Cricket
frequently is **not** in the roster yet clearly poses).

## Cricket judgement (the point of this dataset)
Cricket = a foul-mouthed astromech (a.k.a. R2-CT, reg. KRKT, "Cricket McKenzie",
"Crazybot"). Decide one verdict for the log and report it:
- **QUALIFY** — at least one block is fundamentally Cricket's own action/voice
  (`actor:"Cricket"`). He is a participating character.
- **PRESENT_MINOR** — Cricket is physically present in the scene but never gets
  his own pose; he only appears woven inside another character's poses (e.g.
  "her astromech buzzes furiously" inside Johanna's block). No `actor:"Cricket"`
  rows result.
- **REFERENCE** — Cricket is not in the scene at all; the name only appears as a
  mention of an absent droid (in dialogue, history, or narration).

## Output
1. Write the finished rows to `data/dataset/<NAME>.jsonl` (same row order and
   `seq`s as the pre-parse; meta rows first, then body rows). Each row:
   `{"seq":int,"type":...,"actor":name-or-null,"text":...}` (meta rows also keep
   `"key"`). Do not alter `text` except a split as allowed above. Keep `%t`/`%r`.
2. Return a compact JSON verdict (this is your final message, nothing else):
   `{"name":"<NAME>","verdict":"QUALIFY|PRESENT_MINOR|REFERENCE",
     "cricket_rows":[seqs...],"total_rows":int,"reason":"one sentence"}`

## Hard rules
- ASCII only in any text you print to the console; the JSONL file is UTF-8.
- Never invent or reorder content. The JSONL must reconstruct the scene faithfully.
- Windows username is `evergr3n` (no second 'e') if you touch absolute paths.
