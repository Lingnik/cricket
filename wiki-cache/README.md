# wiki-cache

A local cache of the **Star Wars MUSH (SW1) community wiki**, bundled so the Cricket bot can
resolve citations in the player profiles to full source text offline.

## Contents

- `pages/<slug>.txt` — one wiki page per file (~7,395 pages): a short metadata header
  (title, namespace, last-edit, and for RPlogs the characters/date/factions) followed by the
  raw wikitext.
- `index.jsonl` — one JSON record per page: `{title, ns, ns_name, path, last_edit,
  characters[], rl_date, aby_year, factions[], summary}`. This is the search index.

Resolve and search it with the scripts in [`../tools/`](../tools/) (`lookup.py`, `search.py`).
Regenerate it with `../tools/build_cache.py` from a `sw1mush-wiki-export` directory.

## Source & license

Content is mirrored from **sw1mush.fandom.com** (the SW1 MUSH wiki on Fandom). Fandom user
contributions are licensed under **Creative Commons Attribution-Share Alike (CC-BY-SA)**.
This cache is a redistribution of that content under the same license, with attribution to
the SW1 MUSH wiki and its contributors. It is provided for archival and fan use; no copyright
in the underlying Star Wars properties is claimed.
