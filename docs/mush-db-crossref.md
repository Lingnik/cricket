# In-game DB cross-reference (player vs NPC authority)

Source: live SW1 MUSH DB dumps fetched over Tailscale SSH from
`kali@100.88.188.43:/home/kali/git/sw1-archive/main/dumps/`, cached at
`knowledge/sources/mush-dump/{enum.dump,enum-players.dump}`.

- `enum.dump` — every dbref: `#<n> <FLAGS> <name>` (12,098 clean objects;
  the rest are batch markers / `Bazil/PAGE_CURSOR` echoes, filtered).
  First flag letter = type: **P**layer, **T**hing, **R**oom, **E**xit.
- `enum-players.dump` — the 1,391 Player objects (the canonical player roster).

## Why this matters
It gives an authoritative answer to "is this name a real player or an NPC?" —
the axis we need to attribute poses to both a **character** and a **player**.

Two structural facts the dump confirms:
- **Players are single-token first names**: `Johanna` (#9407), `Crestian`
  (#5921), `Bazil` (#9199), `Lynae` (#9311), `jessalyn` (#3146). So the wiki
  character "Johanna Siri te Danaan" resolves to player **Johanna** by first
  token. (Names use `_` for spaces in-DB.)
- **Cricket is `#8720 TOXnp Cricket` — a Thing with the puppet (`p`) flag, not a
  player.** In-game proof he is an NPC puppet, owned and voiced by a player.
  Other modern NPCs confirm the pattern: `R2-D2` (#5736), `Veruca Violet`
  (#12108 Tn), `V1C3` (#12106), `Vanilla` (#12107).

## Classifying the 1,255 header candidates against the DB
(`data/dataset2/_candidate_db.csv` — candidate, logs_listed, string_matches,
db_type, match kind, dbref, flags)

| class | candidates | share | weighted by string-matches |
|---|---:|---:|---:|
| PLAYER (real player object) | 311 | 25% | 29,021 |
| THING (NPC puppet) | 27 | 2% | 1,050 |
| ROOM | 0 | 0% | 0 |
| UNKNOWN (no DB match) | 917 | 73% | 24,470 |

## The headline: the current DB is a *recent snapshot*, not the historical roster
The 917 UNKNOWN carry nearly as much posing weight (24,470) as the confirmed
players (29,021) — i.e. **~45% of all posing activity is by names absent from
today's DB.** Two causes, both important:

1. **Purged players.** The top UNKNOWN names are heavily-posed but gone:
   `Shenner` (3,305 matches), `Dareus` (1,832), `Morganna` (1,595), `Piper`,
   `Dante`, `Vengan`. These are mostly older-era characters deleted in the
   periodic purges the player flagged. The live DB cannot map them.
2. **Surname / alternate-name variants.** Some UNKNOWN are real, mapped players
   under a different token: `Caiton` is Lynae Cassius-**Caiton** (player Lynae
   #9311); `Dareus` is Antoine **Dareus**. First-token matching misses these
   because the candidate string is the surname.

## Implications for the player->character map
- The DB resolves **311 candidates to live players + 27 to NPC things** with
  certainty — use these directly.
- For the rest, the DB alone is insufficient; the map must also draw on the
  **wiki `author=` field** (uploader/controlling player, present on 1,013 logs)
  and the `players/*.md` profiles to recover purged/historical and
  surname-variant players. This is where the user's manual audit against an
  in-game list adds the most value.
- **NPC->owner (player axis for puppets) is not in these dumps** (name+flags
  only, no owner column). To complete the player axis for NPCs like Cricket,
  either an owner-bearing dump (`@decompile`/`owner` field) or the per-log
  `author=` is needed; for solo-authored NPC logs the author *is* the puppeteer.
