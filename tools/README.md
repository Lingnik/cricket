# tools

Python helpers (stdlib only, no dependencies) for building and querying the bundled
[`../knowledge/runtime/wiki/`](../knowledge/runtime/wiki/). The Cricket bot uses `lookup.py` /
`search.py` to resolve citations in the
[`../knowledge/sources/players/`](../knowledge/sources/players/) profiles to full source text.

## `lookup.py` — resolve a citation to a full page

Profiles cite logs as `(RPlog:Title, date)` and articles as `(Article: Title)`. Pass the
title to print the raw page:

```sh
python3 tools/lookup.py --title "RPlog:Jessa Drops a Bomb"
python3 tools/lookup.py --title "Jessalyn Valios"     # an article (Main namespace)
python3 tools/lookup.py --title "..." --meta-only      # header only, no wikitext
python3 tools/lookup.py --slug Jessalyn_Valios         # by cache filename slug
```

Title match is exact-first, then case-insensitive, then with/without a namespace prefix
(`RPlog:`, `Story:`, `Report:`, …).

## `search.py` — find pages, get handles

Returns titles you can feed back to `lookup.py`. Filter by structured fields and/or match a
term (against title+summary by default, or full text with `--grep`):

```sh
python3 tools/search.py "cloud city"                      # term in title/summary
python3 tools/search.py --character "Jessalyn Valios"     # logs featuring her
python3 tools/search.py --character "Lorn Rhys" --aby 34  # by in-universe (ABY) year
python3 tools/search.py "taser" --grep                    # term in full page text
python3 tools/search.py --character X --ns 100 --limit 50 # ns 100 = RPlog, 0 = article
```

## `build_cache.py` — (re)generate the cache

```sh
python3 tools/build_cache.py --export-dir ~/git/l/sw1mush-wiki-export --out wiki-cache
```

Reads the export's `all_pages.jsonl` (every page) + `log_index_v2.jsonl` (per-RPlog
metadata) and writes `wiki-cache/pages/` + `wiki-cache/index.jsonl`. Idempotent.
