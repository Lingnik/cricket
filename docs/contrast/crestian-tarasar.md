# Contrast Report: Crestian Tarasar

Comparing two documents about the SW1 MUSH character **Crestian Tarasar**:

- **DOC A** — `/home/kali/git/l/cricket/players/players/crestian-tarasar.md` — our new from-scratch OOC bot profile (player-knowledge for a chatbot: concise, fetch-on-demand, recognize-and-converse).
- **DOC B** — `/home/kali/git/l/sw1mush-wiki-export/crestian_caspar_deepdive.md` — the existing literary deep-dive (a 340-line dossier prepared for Taylor's Bazil-return campaign, oriented around two specific plots, "The Last Director" and "The Wedge").

These have **different purposes** and are judged against their own goals below, not against each other.

---

## 1. Purpose fit

**DOC A — fit for purpose: strong.** It is exactly what a bot-facing player profile should be. It opens with a player-identity table (wiki account, alts, activity era, faction, footprint), then a "Talking to them OOC" section with concrete conversation hooks and tone, then a capsule bio with a chronological "fetch handle" arc, a relationships list with log-counts, a playstyle/themes breakdown, and a ranked source list "most useful first." Every beat is citation-tagged (Article / RPlog), which supports fetch-on-demand retrieval. It correctly distinguishes player (Tarasar, a Wizard/admin) from character. It is the right length for a system-promptable, recognize-and-converse asset: ~175 lines, scannable, sourced. It even pre-empts two likely errors (the non-existent "Caspar" alt; Malign vs. Malus).

**DOC B — fit for purpose: strong, but a different purpose.** It is a literary/strategic dossier, not a player profile. Roughly 60% of it (§4 Seams, §5 Bazil Angles, §6 Open Canon) is *campaign tooling* for Taylor's own character to attack the Union — it is not "who is this player and how do I talk to them," it is "how does my character exploit this character." It is far richer on in-fiction biography, the moral ledger, the state anatomy of Caspar, and the secret/subtext layer. Judged as a deep-dive it is excellent and self-aware (it flags its own inferences vs. text, and flags a canon error in a *third* doc). But it would be unusable as-is for a bot: too long, plot-spoilery, and addressed to a specific player's agenda rather than neutral.

---

## 2. Coverage overlap

Both cover the same skeleton, and DOC A's spine is clearly a faithful condensation of the same source corpus:

- **Origins**: Trinumvira/Caspar, 10 BBY; diplomat father, schoolteacher mother; move to Chandrila over "moral cowardice" of neutrality.
- **Career arc**: Brionelle academy → NR Navy ethics instructor / Associate Academic Dean → Imperial Blitzkrieg ends it → evac on the CR90 *Argent Drake* → disillusion → smuggling at Silver Station / Dragonflower Nebula.
- **Sith service**: Darth Malign's New Sith Order; Admiral of Task Force 77; flagship Interdictor *Leviathan*; Duke of Dragonflower; "least traditionally Sith" framing; **not Force-sensitive**; the "have an exit strategy" lesson.
- **The purge survival**: parking the *Leviathan* in the nebula, surviving Aldus Thel's purge as a harmless eccentric.
- **Interregnum/fatherhood**: Firrerreo wife (unnamed); daughter Atsvara (22 ABY, "balance").
- **Mergansar arc**: Malign's return via Johanna; Sariphage plague; Casulmis paramilitary; the Mergansar Incident (*Leviathan* vs. four ships, Sar Admiral killed, ship crippled).
- **Rise to power**: The Mission charity (with Sith money), Twin Suns Hospital, Praecet party with Zaalbacca, 7-of-9 seats, elected Presav, Legacy coalition, the Imperium mutual-protection pact.
- **Statesman era (30–34 ABY)**: reunification, Charros IV admission, the Axel Vichten relationship, Lynae Cassius, the Darth Malus problem.
- **Relationships**: Elana Tracer, Atsvara, Axel, Johanna, Lynae, Malign, Zubindi, Drayson Honos.
- **Voice/themes**: erudite, dry, self-deprecating about verbosity; politics/diplomacy/intrigue dominant; Sith-as-creed; dandy-as-cover.

DOC A hits every one of these in compressed form. The overlap is high and accurate — the profile is not missing the *shape* of the character.

---

## 3. Facts in B missing from A (most significant)

DOC B is much darker and more granular. The biggest omissions in A, roughly in order of importance:

1. **The "buried lies" / villain-beneath-the-statesman thread.** This is B's central thesis and A barely touches it. A presents Crestian as a "redeemed-ish Sith statesman" and "the least cartoonishly-evil Sith." B argues the opposite: that he is a fully ruthless operator the *text* never frames as a villain. Specifically A omits:
   - **Task Force 77 was a dirty-tricks/intelligence outfit** — "false flag operations, and political sabotage" (Article: Leviathan). A says "Admiral … flagship the Interdictor *Leviathan*" but not that he ran the NSO's sabotage/spymaster fleet. *Worth a one-line add* for accuracy of character flavor.
   - **The Mergansar blockade**: he later blockaded/starved Mergansar, demanded 30 trillion credits, and engineered its government's violent collapse "without direct involvement by Caspian forces," then annexed it. A's arc jumps from the Mergansar Incident straight to "reunites the Union's member worlds" and never mentions the blockade. This is a major arc beat.
   - **The Casulmis assassinations**: bombing the Mergani Governor, Lieutenant Governor, and Minister of Justice.
   - **The Mergansar Incident secret**: Malign was secretly aboard and actually won the battle; the "fought four ships to a draw alone" legend is a cover story; Crestian sabotaged the forensic investigation. A presents the Incident at face value as "a stain he still wears."
   - **The Mission is ~75% Imperium/Sith-funded** (named donors incl. Damion I, Honos, Sentinel, Tracer, Johanna), exposed by Wookieeleaks during the 29 ABY election. A says only "with quiet Sith money" — true but understated.
   - **Constitutional gerrymandering**: he wrote the FPTP electoral system and packed refugee seats to win it.

2. **Prae Kichakressa** — the killed Sar Admiral has a name, a homeworld (Krittain Major), and a long shadow (she's why Krittain stayed out of the Union for years). A refers only to "the Sar Admiral killed."

3. **Key household figures A omits entirely:** **Janus Tarasar ("Siege")**, Crestian's cousin and family enforcer; **V1C3** (HK-47-derived droid adjutant); **T3-A7** (Cricket's girlfriend — a direct line into the Cricket-bot project); **Meridian Tarasar** (open-canon relative). A names Zubindi, Atsvara, and the retired Sadim Gnik but not these.

4. **The Caspian state anatomy** (B §3): parties (Praecet 17 / Legacy 11 / Lijsttrekker 6 / Holicet 5), the Union Council/Presav/Vice-Presav structure, **Cas Mos** as Vice Presav, the Caspian Intelligence Service built from his old Sith spy crew with sections on Krittain/Tatooine, the four-fleet Navy, the demographics (47% Human / 28% Sarian / 15% Wookiee). A mentions Caspar lore as a "happy place" hook but carries none of the governmental specifics.

5. **His private, self-aware ruthlessness** (B's voice section): colour-coding personas by outfit (red/green/black for personal/Caspar/Sith); calling his own life's work "war crimes" lightly over dinner; "grieves sincerely and exploits the grief simultaneously." A captures the *register* (dry, self-deprecating) but not this darker self-knowledge.

**Recommendation:** A few of these are worth folding into A as one-line flavor for richer conversation — particularly (1) the Task Force 77 sabotage role, the Mergansar blockade, and the Mission's funding scale, and (3) V1C3 / T3-A7 (the latter especially given the Cricket-bot context). The rest (state anatomy, seams, Bazil-attack angles) are plot tooling and correctly *excluded* from a neutral bot profile.

---

## 4. Anything A gets wrong, or that B contradicts

No hard factual contradictions were found — A is well-supported throughout and the two agree on every dated beat they share. The discrepancies are of **emphasis and completeness**, not fact:

- **Tone/framing divergence (the main one):** A calls him "the *least* cartoonishly-evil Sith" and "redeemed-ish." B explicitly rejects "redeemed" — its thesis is that he never renounced anything, still holds the Duke title, still flies the Sith flagship, still works "Sith matters," and is a Sith intelligence officer running a republic. Both cite the same wiki line ("comparatively easy going … in an organisation filled with … homicidal maniacs"), but B notes that line is *self-written propaganda*. **B is better-supported here** because it quotes the private logs (RPlog:For the Good of Caspar) where Crestian admits the ends-justify-means calculus; A's "redeemed-ish" reads slightly too generous. A's own caveat ("openly plays the flamboyant eccentric dandy as cover") points the same direction, so this is a softening, not an error.
- **"A stain he still wears" (Mergansar Incident):** A treats this as straightforward regret; B shows it is a *managed secret built on a hidden Sith intervention and a sabotaged investigation*. A isn't wrong that he wears it publicly — but the public framing is itself the cover, which A doesn't flag.
- **"with quiet Sith money" (The Mission):** Accurate but materially understated vs. B's documented ~75% figure and the Wookieeleaks exposure.

Net: A contains nothing that B disproves. Where they differ, B is the deeper-sourced and A is the safer/more surface read — appropriate to a public-facing bot, but A leans a touch hagiographic.

---

## 5. Anything A captures that B lacks, or that is fresher

A is genuinely stronger or fresher in several bot-relevant respects:

- **The player-is-a-Wizard OOC note is front-and-center in A and is the single most operationally important fact for a bot.** A states the player "has been elevated to serve as a Wizard," is the Caspian-org and wiki admin, and should be treated as production staff who may hold campaign-secret knowledge. B mentions the player only as Tyler... no — B never flags the *Crestian player's* Wizard/admin status at all (B is focused on the in-fiction character for Taylor's use). This is a clear A win and exactly the kind of OOC, recognize-the-human metadata a bot needs.
- **Player-identity metadata generally:** wiki account name, the full alt roster (Zubindi, NPC Atsvara, retired Sadim Gnik), the 2018 return at Tyler Damion's-player's invitation, 54-log footprint, log-count-per-relationship. B has the in-fiction relationships but not this OOC scaffolding.
- **The explicit "no Caspar alt exists" correction** and the **Malign-vs-Malus disambiguation** — A pre-empts two specific confusions a bot would otherwise make. (B also keeps Malign/Malus distinct but does not call it out as a warning.)
- **Quantified playstyle/themes** (politics 38, diplomacy 26, intrigue 18, etc.) — a compact, bot-friendly characterization B doesn't provide in this form.
- **Recency framing:** both reach 34 ABY / ~2025; neither is staler. A's chronology is cleaner for quick orientation. (B has slightly more 34-ABY texture via the raw logs, but A is not behind.)

The one place B is fresher *and* relevant to A's own ecosystem: the **T3-A7 = Cricket's girlfriend** and **Atsvara's droid-rights revolution / ties to Johanna's Cricket** details. A mentions Atsvara's tie to "Johanna's Cricket" once but doesn't surface T3-A7.

---

## 6. Tone / format / length

- **Length:** A ~175 lines / one screen-and-a-half; B ~340 lines and far denser per line (a full 7-section dossier with tables). B is several times A's word count.
- **Format:** A uses a player table + hook bullets + capsule + arc bullets + ranked-source list — modular, retrieval-friendly, every claim citation-tagged. B uses numbered chapters (§0–§7), a moral "ledger" (Column A / Column B), rated "seam" entries (★–★★★★★), penetrability tables, and a multi-paragraph brief-back. B is essay-and-analysis; A is reference-card.
- **Tone:** A is neutral-to-warm OOC guidance ("Ask about the Union's politics and you've found his happy place"). B is analytical and adversarial ("the smartest, most patient, most successful villain-shaped person … who has never once been treated as a villain by the text") — written to help a rival character break him.
- **Audience:** A addresses a bot operator who needs to recognize and converse with the player. B addresses Taylor, weaving in his own character's vantage (Bazil, Krittain, NRI) and even correcting a third document. B is unusable for a neutral bot without heavy stripping; A is purpose-built.

---

## 7. Verdict

**The new approach (A) is a viable, well-built bot profile and a sound *complement* to B — not a replacement, because they serve different jobs.** A is the right artifact for recognize-and-converse: concise, sourced, OOC-aware, with the player's Wizard/admin status correctly foregrounded (which B lacks). It faithfully condenses the same corpus B drew from, with no factual errors and two useful built-in disambiguations. B remains the place to go for the deep biography, the moral subtext, the Caspian state anatomy, and plot-attack tooling — most of which is correctly out-of-scope for a bot.

**Concrete suggestions to improve A:**

1. **Add one line on the Task Force 77 sabotage role** — "ran the NSO's false-flag/political-sabotage fleet" — so the Sith-era isn't just "Admiral with a big ship." Improves conversational depth.
2. **Add the Mergansar blockade beat** to the arc (currently jumps Incident → reunification). The blockade/30-trillion-demand/engineered-collapse is a major arc beat and a likely conversation topic.
3. **Soften "redeemed-ish."** B (and A's own "dandy-as-cover" note) supports "never actually renounced anything — still holds the Duke title, still flies the Sith flagship." A neutral bot should not over-credit redemption.
4. **Quantify the Mission funding** — "largely Sith/Imperium-funded (exposed during his election)" beats "quiet Sith money."
5. **Add V1C3 and especially T3-A7** to the household/relationships — T3-A7 is Cricket's girlfriend, a direct hook into this very project; and name-drop cousin **Janus "Siege" Tarasar** as the family enforcer.
6. **Optional:** add a one-line "Caspar at a glance" governance note (Presav + Union Council + Cas Mos as Vice Presav; parties Praecet/Legacy/Lijsttrekker/Holicet) so the bot can field basic civics questions about his sandbox without pulling the full dossier.

These are additive polish; none requires restructuring. A is good to ship as the bot asset, with B retained as the fetch-deep source behind it.
