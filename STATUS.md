# Cricket -- project status (plain-language)

## What Cricket is

Cricket is a chatbot that role-plays a specific character inside an old-school,
text-based online game. The game is a "MUSH" -- picture a multiplayer world made
entirely of text, where people log in and act out scenes together, like collaborative
improv theater. Players connect, type things, and read what everyone else types.

The character "Cricket" is a foul-mouthed, scheming little astromech droid (an
R2-D2-style robot, but rude, vain, and unhinged -- he tasers people and rants in ALL
CAPS). He is a real character with a ~24-year history in this game world.

Our bot logs into the game like a player, reads what people say to it, and talks back
*as Cricket*, using an AI model that runs locally on your own computer -- no cloud, no
censorship.

## What we have built (done and working)

- **The bot's "body."** It connects to the game, logs in, joins channels, and correctly
  reads the game's exact text format. We downloaded the game server's own source code to
  get every detail right, and handled its quirks -- including how it tags who *really*
  said something, so the bot can't be fooled by impersonation.
- **A real test game.** Rather than fake it, we built and run an actual copy of the game
  server on an always-on Raspberry Pi, reachable over your private network. The bot is
  connected to it now.
- **The AI brain.** A local, uncensored AI model generates Cricket's words. Uncensored
  matters: an ordinary AI refuses to voice a character this crude.
- **Cricket's actual personality.** We took ~24 years of real role-play transcripts of
  this character (from a public fan wiki) and distilled them into a "character sheet"
  plus a memory of everyone he knows. The result: he sounds exactly like himself.
- **It works end to end, live.** People chat to Cricket on a channel and he replies in
  character; admins can trigger him to act out a scene ("pose") based on what is
  happening in the room.
- **Control + commands.** You can run and steer the bot from your computer, and trusted
  admins can command it from inside the game.
- **A quality-testing system ("evals").** An automated way to score how good and how
  in-character his responses are, so we improve him on evidence, not vibes.
- **Bugs found and fixed by testing.** E.g. his replies were spilling out of the chat
  channel into the room; the role-play feature did not know which room he was in. Fixed.

All of the above is saved and version-controlled.

## What remains

- **Output polish.** The model occasionally emits stray technical junk (leftover
  formatting tokens) and prints his name twice during role-play. Small fixes -- in
  progress.
- **One channel, two jobs.** The "OOC" channel should let Cricket both chat *and* take
  admin commands. Small change -- in progress.
- **A "clean-mode" safety switch.** An optional filter to keep him family-friendly on
  chosen channels. We proved polite instructions do not restrain this uncensored model,
  so it needs a real filter. Deferred -- every channel is fully unhinged for now.
- **Tuning.** Use the testing system to systematically sharpen his voice and behavior.
- **Handoff and go-live.** The "personality" work can move to a separate effort later,
  and the bot gets pointed at the real game when you are ready.
