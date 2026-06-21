# Contrast Report: Bazil McKenzie

**DOC A** — `/home/kali/git/l/cricket/players/players/bazil-mckenzie.md` (new from-scratch OOC bot profile)
**DOC B** — `/home/kali/git/l/sw1mush-wiki-export/bazil_history.md` (existing comprehensive history/background)

---

## 0. SENSITIVITY FLAG (read first)

**No campaign-secret/twist leak detected in DOC A.** This is the most important finding, so to be
precise about what was checked:

- DOC B is explicitly framed as Taylor's own character and the seed material for a **"return
  campaign"** — Section 7 ("Loose Ends as of His Last Appearance") is a list of OOC plot hooks the
  player intends to *play forward*: the blank-page Nelona arc, the closed orphanage, the vanished
  twin Adian, the unwritten Cricket reunion, the Menrai property claim, the unexplained pendant.
  These are *not* secrets so much as un-played threads, but they read as the author's private
  campaign-planning notes.
- **DOC A does not import that planning frame.** It treats Bazil purely as a historical PC, mentions
  the 2007 cameo as a closed past event, and never advertises any of the Section-7 "what happens
  next" hooks as live/forthcoming material. It does not mention the return campaign, the orphanage,
  Adian-as-vanished-twin-to-be-reunited, the Cricket reunion, the Menrai claim, or the pendant.
- DOC A's own footer says *"Sensitivity: none flagged — all material is public wiki canon."* That
  self-assessment is **correct**: everything in DOC A is sourced to public wiki articles and public
  RP logs, with no forward-looking twist material.

**One soft note, not a leak:** DOC A's footer reveals the OOC identity inference that *"Vauki and
Jonau Diggs are not separate characters — they are Bazil's NRI undercover aliases."* In-character,
the whole point of an alias is that others *don't* know it's Bazil. A bot that volunteers "those were
all the same guy" could spoil an IC mystery for a player who scened with Vauki and never learned the
truth. This is alias-unmasking, not campaign-twist material — low severity — but worth gating behind
"only when asked OOC."

---

## 1. Purpose fit

**DOC A (OOC bot profile):** Strong fit. It is built for exactly the stated job — concise,
fetch-on-demand, recognize-and-converse. It opens with a "Talking to them OOC" section (player vibe,
safe conversation hooks), gives a compact arc with each beat tagged as "a fetch handle," ranks source
logs "most useful first," and closes with a sensitivity/PC-vs-NPC note. The structure is
purpose-shaped: a bot can answer "who is this player / what do they like to play / what's a good
opener" without loading the whole corpus.

**DOC B (history/background):** Strong fit for *its* purpose, which is the opposite — a definitive,
exhaustive reference and a campaign-planning dossier for Taylor's own return. It runs deep on
biography, two-sided sourcing (e.g. the man who took Bazil's arms, cited from the attacker's own
article), the full Cricket-to-34-ABY trajectory, and an explicit loose-ends hook list. It is far too
long and forward-looking to drop into a bot prompt, and it isn't trying to be.

Each document is well-matched to its own brief. The risk is only in *direction of copying*: pulling
more of B into A is mostly safe (public facts) **except** B's Section 7 planning hooks, which should
stay out of A.

## 2. Coverage overlap

Substantial overlap on the public-canon spine. Both cover:
- Vital stats (b. 18 BBY, Tatooine-system mining asteroid, human, brown hair / hazel eyes).
- Slave origin → killed his slaver "father" → mercenary flying → IGNews freight → "Galactic Paper Boy."
- Casey Johnson as the vanished lost-love wound.
- Ghost Squadron pilot → XO; Diplo Corps detour under Poguala, then back to StarOps.
- NRI recruitment; undercover as Vauki and Jonau Diggs; Death Star III plot with Xanatos & Mersche
  across Caspar / Cochran / Dreven; the *Angry Rancor* / Gastus destruction scene.
- Rapid promotion → reluctantly running NRI when the Director vanished.
- Morganna/Kacela mind-probe overwhelmed by his insanity.
- Imperial kidnapping, rumored time in the Emperor's company.
- Corellia tangle with Simon Sezirok / Mira / Jessalyn.
- Orson's "dirty little secret" (the torture reveal).
- Arm loss defending Coruscant's shield generators; cybernetics + psych-drug medical file.
- The 2007 / 16 ABY late cameo; family = sister Jasmine + twin brother Adian.

DOC A is essentially a faithful, compressed distillation of DOC B's public-fact layer.

## 3. Facts in B missing from A (candidates to add)

Significant items B has that A omits. Marked **ADD** (safe, enriches recognition/conversation),
**MAYBE**, or **KEEP OUT** (campaign-planning material):

- **ADD — the noble-birth / infant-kidnapping truth.** B's biggest backstory beat: Bazil was
  *kidnapped as an infant* by a slavery ring, sold to the McKenzie mining colony; his blood parents
  were Corellian nobility/medical researchers (the Heretins) killed by the Empire on Mon Calamari for
  refusing to build anti-alien bioweapons. A frames "slaver father" as literal parentage; B reveals
  it was a lie. This reshapes the whole origin and is public canon — a strong recognition hook.
- **ADD — the Jasmine reunion scene (10 ABY, the emotional center).** Bazil learns Jasmine Heretin,
  a long-time friend, is his blood sister, and breaks the news at the Massassi amphitheatre; he gave
  up his chance to see the Death Star plans to do it. A lists Jasmine as family in one line but omits
  this defining scene. Big conversation hook with strong emotional payload.
- **ADD — Adian Ward = his own twin AND his predecessor as NRI Director.** B's irony (Bazil succeeds
  the brother he doesn't yet know is his twin) is a great fact. A names Adian only as "twin brother,
  sole surviving family." *Note: the bare fact is public canon and fine to add; B's framing of Adian
  as a "vanished twin / ready-made reunion plot" is the KEEP-OUT campaign angle — add the fact, not
  the hook.*
- **ADD — more aliases.** B lists **Mege Vauki** (swoop-racer cover), **Xeres**, and **Grassius
  Knoll** (under which he revives Talon Karrde near Pride-1) in addition to Vauki / Jonau Diggs. A
  has only two. (Same alias-unmasking caution from §0 applies — list them, gate the "all = Bazil" reveal.)
- **ADD — the named maimer: Camrath Kizuka**, the Imperial officer who "tore off at least two of his
  limbs," corroborated from the Third Battle of Coruscant / Camrath Kizuka articles. A says only that
  he "loses both arms." The named, two-sourced antagonist is a recallable hook.
- **MAYBE — Emperor Valak** named as commander of Death Star III; A leaves the DSIII commander
  unnamed.
- **MAYBE — color personality detail:** out-bluffing Lando at sabacc, serenading a lounge, appearing
  "wrapped in a sheet wielding a sword," the choking-on-a-cracker coma. Great voice texture; A's
  voice section is thinner here.
- **MAYBE — ships:** *The Dirty Jawa* (his home/final stage, Cricket painted on the hull) and
  *Dawntreader* microfreighter. A mentions neither; the Dirty Jawa is a strong prop hook and ties to
  Cricket.
- **MAYBE — Cricket connection itself.** Given this is the **cricket** repo, it is notable A's Bazil
  profile never mentions that Cricket was originally Bazil's droid. Worth a one-liner cross-reference
  (without importing B's whole 34-ABY corporate trajectory).
- **MAYBE — "Legend" status / never killed off** — B notes he is categorized as a Legend and left
  alive. Minor but a nice OOC framing point.
- **KEEP OUT — Section 7 loose-ends hooks** (Nelona blank page, the orphanage, the unwritten Cricket
  reunion, Menrai property, the pendant, conditional sanity failsafe). These are the return-campaign
  planning layer. Do not add to a public bot corpus.

## 4. Anything A gets wrong / B contradicts

No hard factual contradictions on the public spine; A is accurate where it overlaps. Minor points:

- **Origin framing (already covered):** A presents the slaver as Bazil's actual father ("escaped by
  murdering his slaver father"). B is better-supported: the McKenzie was a *foster/captor*, the
  killing is real, but the *paternity* is part of the slavery-ring lie. A isn't "wrong" about what
  Bazil long believed, but it omits the canonical correction. B is better supported.
- **Date/era labeling differs but isn't contradictory.** A tags the NR-pilot/Ghost Squadron entry as
  "8–9 ABY" and the Casey/IGNews era as "pre-8 ABY"; B places the Deliverance/pilot debut at 8 ABY
  (late 1999) and the Director years at 10 ABY (2001). The 1999→8 ABY, 2001→10 ABY mapping in B is
  the more careful one. A's "9 ABY" tags on several 2000-dated logs are consistent with the game's
  offset, so this is labeling granularity, not a conflict. Worth aligning A's Director beat to **10
  ABY** to match B (A implies the Director role at 9 ABY).
- **Gender descriptor:** B records the canonical (and player-defended) listing "Castrate Male." A
  omits it. Not wrong to omit in a bot profile — arguably tactful — but it's a real public-canon
  datum if completeness is wanted.

## 5. Anything A captures that B lacks / is fresher

- **Quantified footprint.** A gives concrete numbers — 67 logs, ~60 self-uploaded, faction split (NR
  62 / NRI 20 / Empire 12), theme tallies (espionage 21, intrigue 14, Death Star 11, diplomacy/
  politics 10 each, recruitment 7), and a *most-frequent-partner* count (Altair Quila, 15 shared
  logs; Luke 9; Eva Sargent 8). B describes the corpus qualitatively but doesn't tabulate it. These
  numbers are genuinely fresher and directly useful for "what does this player like to play."
- **Player-behavior read.** A's framing of Bazil's player as a "self-documenting old-guard player who
  uploads his own logs" and "writes a lot of solo/two-hander material" is an OOC-meta observation
  tuned for the bot's recognize-the-player job; B is in-fiction and doesn't characterize the player's
  habits this way.
- **Eva Sargent** as a recurring Caspar contact appears in A's relationship list but not in B's cast
  network — a small coverage gain.
- **Ranked "start here" orientation.** A's "Dig deeper — ranked source logs" (Article first, then the
  five or six most orienting logs) is a usability layer B doesn't provide; B's article-survey
  (Section 4) is exhaustive rather than prioritized.

## 6. Tone / format / length

- **Length:** DOC A ≈ 135 lines / one screen-and-a-half; DOC B ≈ 168 lines but far denser, with
  longer paragraphs and a full second subject (Cricket's 34-ABY arc). B is several times A's word
  count and reading load.
- **Format:** A — header info-table, themed prose sections, bulleted arc with inline "(fetch handle)"
  cues, a ranked source list, a footer sensitivity/PC note. Built for retrieval. B — numbered
  reference sections (1–7), heavy inline citations, vital-stats blocks, a dedicated loose-ends/hooks
  list, a compilation footer. Built for completeness and campaign planning.
- **Tone:** A is OOC-meta and conversational ("a fun 'wait, that was *him*?' thread," "easy,
  low-stakes opener") — it talks *about* the player to a bot operator. B is an in-universe-grounded
  scholarly dossier — it talks *about the character and the fiction* to the author. Both are
  well-written; the registers correctly match their purposes.

## 7. Verdict

**Viable for bot use — yes.** DOC A is accurate, well-structured for fetch-on-demand, correctly
purpose-shaped, and — critically — **contains no return-campaign twist leak**. It can ship.

Concrete improvements to A, in priority order:
1. **Add the public-canon biography beats that most change recognition:** the infant-kidnapping /
   noble-Heretin-birth truth (correcting the literal "slaver father"), the Jasmine "you are my
   sister" reunion, Adian-as-twin-and-NRI-predecessor (fact only), and the named maimer Camrath
   Kizuka. These are all public and high-value.
2. **Round out the alias list** (add Mege Vauki, Xeres, Grassius Knoll) — but **gate the "all of
   these are the same person" reveal** behind an explicit OOC question, since it unmasks IC covers.
3. **Add a one-line Cricket cross-reference** (Cricket was originally Bazil's droid) — apt for this
   repo — without importing B's modern corporate trajectory.
4. **Align the Director beat to 10 ABY** to match B's cleaner date mapping.
5. **Do NOT import B's Section 7 loose-ends/hooks or any "return campaign" framing.** Keep
   forward-looking plot material out of the public bot corpus.
6. Optionally add a couple of B's color beats (the Lando sabacc bluff, the sword-and-sheet entrance)
   to thicken A's voice section, and the *Dirty Jawa* as a prop hook.

---

*Sources read in full and unmodified. No commits made.*
