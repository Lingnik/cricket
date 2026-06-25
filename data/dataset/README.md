# Cricket RP-log turn dataset

Per-log JSONL turn-data extracted from the SW1 MUSH wiki cache
(`knowledge/runtime/wiki/pages/RPlog_*.txt`), for fine-tuning an RP LLM on the
astromech **Cricket**. One file per RP log; one JSON object per line.

## Scope: logs where Cricket is a character in the scene
Of 36 wiki RP logs that mention Cricket or an alias (`R2-CT`, `KRKT`,
"Cricket McKenzie", "Crazybot"), this directory holds the **14** in which he is
actually present. The other 22 only *reference* an absent droid and were moved
to `_rejected/` (kept for audit). Each log's verdict:

- **QUALIFY (8)** — Cricket has his own poses (rows with `actor:"Cricket"`).
- **PRESENT_MINOR (6)** — Cricket is physically in the scene but only ever woven
  inside another character's poses, so he yields no `actor:"Cricket"` rows.
- **REFERENCE (22, in `_rejected/`)** — name-only mention of an absent droid.

See `MANIFEST.md` for the table and `_verdicts.json` for the per-log reasons.

## Supplementary: `cricket_embedded.jsonl`
In the PRESENT_MINOR logs Cricket is voiced *inside* another character's pose
(almost always Johanna's), so those scene files contain no `actor:"Cricket"`
rows. `cricket_embedded.jsonl` carves his own dialogue and the third-person
descriptions of his actions out of those host poses into **20** standalone
Cricket poses, each tagged with provenance (`source_log`, `source_seq`,
`host_poser`, `kind` = dialogue/action/mixed, `derived:true`). Other astromechs
in those battle scenes (Shorty, Nate, the "red astromech") are excluded.
Combined with the 40 native poses in the QUALIFY files, this gives **60**
Cricket training poses. Train on native `actor:"Cricket"` rows + this pool;
do not also feed the host blocks, or the carved text double-counts.
Regenerate with `python tools/carve_cricket.py` (anchor-sliced, verbatim-checked).

## Row schema
```json
{"seq": 0, "type": "meta", "key": "title",  "actor": null,      "text": "..."}
{"seq": 7, "type": "pose", "key": null,       "actor": "Cricket", "text": "..."}
```
- `seq` — row order within the log (contiguous from 0).
- `type` — `meta` (page/infobox fields), `pose` (a character's turn),
  `scene` (establishing narration / room description, no actor),
  `desc` (in-scene description of a character/object), `ooc` (out-of-character).
- `actor` — canonical character name for `pose` rows; `null` otherwise.
- `text` — the turn, concatenated to one line in MUSH convention:
  **indentation -> `%t`**, **newlines -> `%r`**. Wiki markup is stripped
  (`[[link|disp]]` -> disp, HTML entities decoded, `''`/`'''` emphasis removed).
- `meta` rows also carry `key`; the `characters` meta row carries a `roster` list.

## Rebuilding
```
# 1. deterministic pre-parse (mechanical: segmentation, cleanup, %t/%r encoding)
python tools/rplog_to_jsonl.py <page.txt> --out data/dataset/_preparse/<NAME>.jsonl
# 2. attribution pass (actor + type labels + Cricket verdict) per tools/ATTRIBUTION_PROTOCOL.md
# 3. index + manifest
python tools/dataset_index.py
```
`_preparse/` holds the stage-1 output (actors unlabeled); the files here are the
finished, attributed dataset.
