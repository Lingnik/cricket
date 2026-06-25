# Name resolution & the two attribution axes

Each pose row carries two axes:
- `actor` — the **character** as labeled in the log (the RP name, left as-is).
- `player` — the canonical **player handle** the character resolves to, or `""`
  when unresolved.

`name_map.csv` maps every variant -> `player` / `dbref` / `db_type` / `source`.

## Resolution policy (final)
Sources, in priority order:
1. `exact` / `exact-thing` — variant matches a live MUSH object name (players
   from `finger.jsonl`, NPC things from `enum.dump`).
2. `full_name` / `alias` / `token` / `fuzzy` — resolved via the finger
   `full_name`/`alias` fields or a name token (e.g. `Lorn Rhys` -> player
   **Malus** via full_name; `Luke Skywalker` -> **Luke** via token).
3. `annotation` — hand-mapped in `names_3_nomatch.csv:bazil_added` (purged
   players and NPC controllers, e.g. `Etiel te Danaan` -> Johanna).
4. `two-part` — **unresolvable; the full two-part log name is kept as the
   character's own identity** (no player). ~55% of historical names: purged
   accounts the live DB cannot recover.

## Sources & caveats
- DB dumps: `knowledge/sources/mush-dump/{enum.dump,enum-players.dump,
  finger.jsonl,finger.csv}` (live tailnet snapshot). The flag parser accepts
  non-letter flag chars (e.g. `~`) and drops `#-1 NO SUCH OBJECT` garbage.
- finger covers **current accounts only**, so it cannot resolve purged players;
  those rely on the `bazil_added` annotations or stay two-part.
- NPC things (Cricket #8720, Atsvara #12102) resolve on the character axis but
  not the player axis — their owning player isn't in these name+flags dumps.
- Audit trail: `names_1_exact.csv`, `names_2_close.csv`, `names_3_nomatch.csv`.
