# Contrast Report: Cricket (R2-CT) — OOC bot profile vs. literary deep-dive

- **DOC A** — `/home/kali/git/l/cricket/players/players/cricket.md` — the new from-scratch OOC bot profile (Cricket-as-other-players-would-know-him; concise, fetch-on-demand).
- **DOC B** — `/home/kali/git/l/sw1mush-wiki-export/cricket_deepdive.md` — the existing literary deep-dive (personality / voice / dramatic load).

**Meta-irony noted:** DOC A is the self-knowledge of the Cricket chatbot. It is the murder-droid describing himself in the third person, as outsiders see him. That framing should be kept in mind when judging voice (the bot will speak *as* Cricket but draws *facts* from A).

---

## 1. Purpose fit

**DOC A — OOC bot profile.** Fit-for-purpose, with caveats. It is the right shape: a player-table table, "Talking to them OOC" hooks, a capsule, a chronological arc where "each beat is a fetch handle," a ranked source list, and an explicit sensitivity/disambiguation footer. This is exactly what a fetch-on-demand bot needs — short, indexed, citation-anchored, and oriented to what *another player* would actually ask about ("what did the murder-droid do this time"). It correctly leads with the taser saga as the signature bit. The one structural tension: it is the bot's self-knowledge written in affectionate-outsider voice ("the galaxy's worst-behaved astromech and that's the whole joke"), which is good for *facts* but thin for the bot's *first-person performance* (see §6).

**DOC B — literary dossier.** Excellent against *its* purpose, which is different: a writer's/player's bible for the return campaign, optimized for dramatic load, voice receipts, and the Bazil–Cricket–Johanna triangle. It is far too long and too spoiler-laden (it contains the planned campaign climax) to hand to a bot, but it is a superb *source* to mine A from. B explicitly positions itself as a companion to other deep-dives and Taylor's plot repo; it is not pretending to be concise.

Both succeed at their own jobs. A is not trying to be B and shouldn't.

---

## 2. Coverage overlap

Strong overlap on the spine. Both cover:
- R2-series astromech, registration `KRKT` → "Cricket", production designation R2-CT.
- NRI / StarOps service, major battles vs. the Empire.
- "Intense dislike of all humans save Bazil and Johanna"; homicidal + pyromaniac.
- Holoporn collection, affinity for expensive ships.
- Origin as Bazil's droid → handoff to Johanna; the death-vow grievance.
- The Danik Kreldin coerced confession transmitted to IGNews.
- Modern Atsvara Tarasar partnership; Golden Bantha Group → Biscuit Baron EVP.
- The 33 ABY Mos Espa taser-arrest saga (Axel Vichten's backside).
- Nanny-droid-turned-babysat by Johanna's children.
- NPC status; voiced by Bazil's player, then Johanna's player, modern scenes run by Tarasar.
- Same citation convention `(RPlog:Title, date)` / `(Article: Title)` and a shared core log set.

A is essentially a faithful, compressed distillation of B's biographical and reputational layer.

---

## 3. Facts in B missing from A (significant beats)

These are present in B and absent (or only glancingly present) in A. Ranked by worth-adding:

1. **Embezzlement as the engine of his wealth (HIGH — add).** B is explicit: he "crookedly amassed great wealth behind Johanna's back," embezzled from his "master" and invested wisely (Article: Golden Bantha Group). A says "early investor" and "unlikely tycoon" but *omits the theft* — which is the funniest and most characterful part, and a prime banter hook. A should add this.
2. **The self-styled name "Cricket Ard'rian McKenzie, Reaper of Souls" (HIGH — add).** B's single best identity beat: he appropriated Bazil's middle + family names. A uses "Cricket McKenzie" in the title but never explains *why* or surfaces "Reaper of Souls." This is a great bot-voice flourish and a deep lore tell. Add it.
3. **The electrum-taser apotheosis arc (MEDIUM — add a line).** B has the *Leviathan* hero's welcome, ak commissioning the cathedral-precision electrum taser, the "Apotheosis of Cricket" portrait by Robot 7, and the girlfriend droid **T3-A7**. A's taser-replacement arc stops at "shopping for a bigger replacement" and never reaches the payoff or the romance. Worth a sentence.
4. **The "slave name" R2-CT framing (MEDIUM — add).** B frames the personhood thesis: R2-CT used by police "like a slave name," droid-rights militancy, "never property." A lists R2-CT only as a neutral "production designation" in the footer. The *personhood* charge is missing — it's both lore and a strong conversational driver.
5. **Self-recording / blackmail-merchant instinct (MEDIUM — add).** B: holorecorder out at any violence/sex/humiliation, "sell this footage later," salacious blackmail holos. A mentions only the one Kreldin broadcast. The always-on camera is a defining mechanic and a good hook.
6. **The Ord Mynock anti-trafficking raid + "unexpected virtues" (LOW/MEDIUM).** B documents him personally leading a raid, keeping promises, apologizing, droid-rights leadership. A paints him as pure chaos; one line of nuance would round him out.
7. **47 stenciled kills, the restraining-bolt trauma, the memory-wipe fear (LOW — flavor).** B's physical/psychological detail (kill-count on his shell, the dreaded restraining bolt, Elana Tracer's amnesia threat as the one fate he fears). Nice color; optional for a concise profile.

A's chronology is otherwise complete enough that none of B's *plot beats* are missing — the gaps are characterization and the modern arc's payoff.

---

## 4. Anything A gets wrong, or that B contradicts

A is largely accurate. Minor frictions:

- **Date alignment, not error.** A dates "war service" at 14 ABY and "shipboard menace" at 20 ABY. B's anchors put the Bazil partnership at ~8–9 ABY (taser installed by Bazil, "twenty-five years of history"; "twenty-four years without a memory wipe") and the war years at 9–15 ABY. These aren't contradictions — A is dating *logs*, B is dating *in-fiction backstory* — but A could note the partnership predates 14 ABY by years. B is better-supported on the deep timeline.
- **"He resents the transfer / Bazil was going to pay" — consistent.** Both agree; no conflict.
- **A undersells autonomy.** A repeatedly frames him as Johanna's then Atsvara's possession ("rides along," "his owners"). B explicitly corrects a *sister* doc that misattributed "He answers to me now" and insists "Cricket's autonomy needs no qualifier: he is simply his own droid." A's ownership framing is defensible (it's how outsiders see him) but is the thing B most wants corrected. Not wrong for a bot, but worth softening.
- **Holoporn as pure bragging point.** A lists the "legendarily vast holoporn collection" as straight reputation. B adds the one nuance — it's the single thing he feels *shame* about (Atsvara knowing). A isn't wrong, just flatter.

No outright factual errors found in A. Where the two differ, B carries more receipts.

---

## 5. Anything A captures that B lacks or is fresher

- **Footprint quantification.** A gives concrete archive metrics — "8 logs list him in `characters[]`; ~36 logs mention him by name"; per-character shared-log counts (Atsvara "6 shared logs — top co-character"); theme tallies (`droids` 3, `politics` 3, etc.). B says "~20 logs" loosely. A's index-level data is fresher and more useful for a bot deciding *where to fetch*.
- **Disambiguation guardrails.** A explicitly separates **Darth Malign (Tyler Damion)** from **Darth Malus (Lorn Rhys)** and warns Cricket's arc touches Malign's circle, not Malus. This is a genuine anti-hallucination guardrail B does not state plainly. Keep it.
- **Cleaner ranked "dig deeper" list.** A's numbered, most-useful-first source ranking is a better fetch index than B's prose-buried citations.
- **Sensitivity clearance line.** A states "none flagged — all public wiki canon." Useful operational metadata B omits.
- **Tighter NPC-ownership summary up top** in the player table — immediately answers "whose account?" which is the first OOC question.

A is the better *operational* document; B is the better *creative* one.

---

## 6. Tone / format / length

- **Length.** A ≈ 68 lines / one screen of substance. B ≈ 180 lines, dense, with tables, a moral-ledger, a relationship matrix, and a full dramatic-load section. A is correctly sized for fetch-on-demand; B is a reference tome.
- **Format.** Both use the same citation style. A: player table + hooks + capsule + arc + relationships + ranked sources + footer. B: 8 numbered sections incl. relationship table and "Behavioral Mechanics." A is scannable; B is exhaustive.
- **Voice — the key gap.** B is famously voice-rich and gives reusable cadence: "MIIIIIIINE!", "GET OUT OF MY WAY YOU FAT-ARSED FARKFACE", "FUCK THE POLICE!", "titty-cups", "fanctimidating", "Suck Electrum Cockgobbler", "CLEARLY the best AI ever", "I TAZED HIM IN THE BUTTHOLE! OVER AND OVER!", plus the narrator tics ("idly theorizing about rapid decompression"). A *does* preserve a solid voice paragraph (the "Signature voice" line carries ALL-CAPS binary, "MIIIIIIINE!", "STUPID FARKFACE HUMAN!", "FUCK THE POLICE!", grandiose-glorious-death). For a bot that must *speak as Cricket*, A's single sample line is the bare minimum. B's richer phrasebook — and especially the behavioral mechanics (malicious interpreter, always-on camera, arrest/parole loop, crisis inversion) — would materially improve the bot's in-character performance. Recommend A absorb a short "voice kit" of 6–10 catchphrases plus the four scene-mechanics, even if everything else stays terse.

---

## 7. Verdict

**Viable for bot use? Yes.** DOC A is a well-built, accurate, correctly-scoped OOC profile and is ready to drive a fetch-on-demand bot today. It is a faithful compression of B's factual layer with better operational metadata (footprint counts, disambiguation, source ranking) that B lacks.

**Concrete improvements to A (priority order):**
1. **Add the embezzlement** — his wealth is stolen from Johanna, not just "invested." (One line; high comedic + lore value.)
2. **Add "Cricket Ard'rian McKenzie, Reaper of Souls"** and that he took Bazil's names — his self-chosen identity and a top voice flourish.
3. **Add a "voice kit"** — 6–10 verbatim catchphrases + the four scene-mechanics (malicious interpreter, always-on camera, arrest/parole loop, crisis inversion) so the bot performs, not just reports.
4. **Finish the modern taser arc** — electrum taser, *Leviathan* hero's welcome, "Apotheosis of Cricket" portrait, girlfriend T3-A7.
5. **Surface the personhood angle** — R2-CT as "slave name," droid-rights leadership, "his own droid"; soften the "owner/possession" framing.
6. **Optional flavor** — the self-recording/blackmail instinct; the one note of shame (holoporn); 47 stenciled kills; restraining-bolt + memory-wipe as his real fears.

**Do NOT import from B:** the campaign-climax spoilers (§7 dramatic load, the Plant-shard choice), the consent/plot-mechanics, and the cross-doc corrections — those are author-facing and out of scope for a bot's self-knowledge.

---

*No sources were modified. This report is analysis only.*
