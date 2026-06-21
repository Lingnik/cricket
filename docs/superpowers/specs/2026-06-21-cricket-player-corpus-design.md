# Cricket OOC Player-Knowledge Corpus — Design

**Date:** 2026-06-21
**Repo:** `Lingnik/cricket` (public), branch `players`
**Author:** Taylor (Lingnik) + Claude

## Purpose

The Cricket *bot* is an OOC veteran-community persona that chats with other SW1 MUSH
players out-of-character. It needs to recognize a player, know which character(s) they
run, and converse credibly about those characters' histories — pulling full source
material on demand rather than carrying it all in context.

This is **OOC player knowledge** (wiki-level omniscience), distinct from Cricket-the-
*character*'s in-character (IC) knowledge, which is already handled via Cricket's own logs.

## Non-goals

- Not literary deep-dive essays (those exist: `*_deepdive.md` in the export workspace).
- Not IC/in-character memory for Cricket the droid — already covered.
- Not a runtime harness/bot implementation — bot ingestion is deferred (separate effort).

## Scope

Six players active in 2020-or-later logs, measured across their **full-corpus** footprint.
Tarasar (Crestian/Caspar) and BazilMcKenzie (Bazil) are already done and excluded.

| Player account | Character(s) | Full-corpus logs |
|---|---|---|
| JessalynValios | Jessalyn Valios | 152 |
| Axel Vichten | Axel Vichten (+Thurston Unger) | 54 (+4) |
| LtTracer | Elana Tracer | 25 |
| Starfleetdropout33 | Zubindi Hakoon (+Sorin) | 17 |
| IfSoGirl25 | Siarra Krell + Wrexan | 18 |
| SW1Lorn | Lorn Rhys + Darth Malus | 17 |

## Architecture

Three components in the `cricket` repo:

### 1. `players/` — synthesized per-player bios (the deliverable)

One Markdown file per player (named by primary character/handle). Structure:

- **OOC header** — wiki handle(s)/account, activity era (incl. 2020+ status), characters run.
- **Talking to them OOC** — short orientation: themes/tone they enjoy, *recent* storylines
  as conversation hooks.
- **Per character** — capsule (species/faction/role), arc synthesis (chronological, cited),
  key relationships (cited), playstyle/themes, signature voice.
- **Dig deeper** — ranked list of that character's most relevant logs as resolvable handles
  for the bot to fetch.
- **Sensitivity** — any campaign-secret / OOC-wizard concern is flagged to Taylor and NOT
  published without sign-off.

Voice condensed from the existing deep-dives, optimized for fetch-on-demand.

### 2. `wiki-cache/` — bundled cache of the whole wiki (~50MB)

Built from the existing export (`~/git/l/sw1mush-wiki-export/`):

- `wiki-cache/pages/<pageid>.txt` — one raw page per file, all ~7,395 wiki pages.
- `wiki-cache/index.jsonl` — one record per page merging `manifest.json` + `log_index_v2.jsonl`:
  `{pageid, title, namespace, characters[], rl_date, aby_year, factions[], summary, path}`.
- `wiki-cache/README.md` — CC-BY-SA attribution + source note (content from
  sw1mush.fandom.com; required since the repo is public).

### 3. `tools/` — Python lookup/search capabilities

- `lookup.py --title "RPlog:Title" | --id <pageid>` → prints raw page text from cache.
- `search.py "<term>" [--character X] [--aby N] [--year Y]` → filters `index.jsonl` and
  greps `pages/`, returns matching handles (title + pageid + date).
- `tools/README.md` — usage, so the harnessed bot knows how to resolve citations.

## Citation handle format

Bios cite logs as `(RPlog:Title, date)` and articles as `(Article: Title)` — the same
style as the existing deep-dives. `lookup.py --title` resolves by exact wiki title (unique
key), so a citation doubles as a fetch handle.

## Repo visibility / licensing

`cricket` stays **public**. The bundled wiki cache is re-hosted under **CC-BY-SA** with
attribution in `wiki-cache/README.md` (Fandom default license; permits re-host with credit).

## Method (per player, replicating the Cricket precedent)

1. Resolve the player's character(s) from `page_created_by` / `uploader` / `{{NPC}}`.
2. Collect each character's logs two ways and union: index (`characters[]` in
   `log_index_v2.jsonl`) + text grep over `logs_split/` (catches passing poses). Watch
   common-word false positives and name variants/aliases.
3. Read each character's Article in `pages/0_Main/`.
4. Synthesize the bio; cite every claim; rank "dig deeper" logs by relevance.

## Deliverable / integration

Branch `players` → PR against `main`. Commit/push only when Taylor explicitly asks
(per Taylor's git hygiene). Organization within the repo can be revisited later.

## Open questions

None blocking. Lynae Cassius (100 logs) appears heavily alongside SW1Lorn's Darth Malus
in 2024–25 but her own account is not 2020+-active; she features in Lorn's relationships
but does not get her own player file unless Taylor wants her pulled in.
