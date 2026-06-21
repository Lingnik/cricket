"""LlmPersona: turns a Turn into a prompt, calls an InferenceClient, returns a Response.

The message ASSEMBLY follows the cache-stable layout from docs/INFERENCE_BACKEND.md
(most-stable first: system + character bio -> memories/context -> the new turn), so the
Ollama prefix cache stays warm. The prompt CONTENT -- the real character sheet, voice, and
memory weaving -- is owned by phase 2 (the persona session) and lives in the active
profile's `prompts` block; this provides a functional default so a dry-run produces text.

The persona reads the active profile live via `profile_getter`, so edits made through the
HTTP panel take effect without restarting the bot.
"""

from __future__ import annotations

from typing import Callable, Union

from .base import Persona, Response, Turn
from .inference import InferenceClient

# Ollama option keys passed straight through from the profile's inference block.
_PASSTHROUGH = ("num_ctx", "num_predict", "temperature", "top_p", "stop")


class LlmPersona(Persona):
    def __init__(
        self,
        client: InferenceClient,
        profile_getter: Union[Callable, None] = None,
        lore=None,
        wiki=None,
    ) -> None:
        self._client = client
        # () -> active profile doc (dict) or None. Read on each turn so live edits apply.
        self._get_profile = profile_getter or (lambda: None)
        # Optional LoreStore: dossiers for the characters present are injected as a
        # memories block between the stable system prompt and the volatile scene.
        self._lore = lore
        # Optional WikiIndex: in OOC chat, factual blurbs for topics mentioned in the line are
        # injected so Cricket can play "rogue wiki search engine" -- summarize, but crassly.
        self._wiki = wiki

    async def respond(self, turn: Turn) -> Union[Response, None]:
        doc = self._get_profile() or {}
        prompts = doc.get("prompts", {}) if isinstance(doc, dict) else {}
        inference = doc.get("inference", {}) if isinstance(doc, dict) else {}

        memories = self._retrieve_memories(turn)
        messages = self._build_messages(turn, prompts, memories)
        options = self._build_options(inference)
        text = await self._client.complete(
            messages, options=options, keep_alive=inference.get("keep_alive")
        )
        text = (text or "").strip()
        if not text:
            return None
        action = "pose" if turn.mode == "rp" else "say"
        return Response(text=text, action=action)

    def _retrieve_memories(self, turn: Turn) -> str:
        """Dossiers for the characters present in this scene (name-based; channel and
        room speakers are matched against known lore characters). Empty if no LoreStore.

        Scope follows the mode: room RP (`rp`) gets the IC facet (canon-plausible knowledge
        only); channel chat gets the OOC facet (the wider meta/teasing suite)."""
        cast = []
        seen = set()

        def add(name: str) -> None:
            n = (name or "").strip()
            if n and n.lower() not in seen:
                seen.add(n.lower())
                cast.append(n)

        # Speakers present in the scene.
        for line in turn.context:
            add(line.speaker)
        add(turn.speaker)

        blocks = []
        if self._lore is not None:
            # Characters NAMED in the live line or scene, even if absent -- so "what do you
            # know about Johanna?" pulls her dossier. Deterministic gazetteer match.
            for name in self._lore.mentioned(turn.text):
                add(name)
            for line in turn.context:
                for name in self._lore.mentioned(line.text):
                    add(name)
            scope = "ic" if turn.mode == "rp" else "ooc"
            dossiers = self._lore.retrieve(cast, scope=scope)
            if dossiers.strip():
                blocks.append(dossiers)

        # OOC only: wiki blurbs for topics named in the line (the "rogue search engine"). IC
        # stays canon-grounded. Exclude the bot itself and anyone already covered by a dossier.
        if self._wiki is not None and turn.mode != "rp":
            bot = turn.bot_identity.name if turn.bot_identity else ""
            exclude = set(cast)
            if bot:
                exclude.add(bot)
            topics = self._wiki.topics(turn.text, exclude=exclude)
            if topics:
                lines = ["What the records say (you may summarize, but stay in character):"]
                for title, blurb in topics:
                    lines.append("- %s: %s" % (title, blurb))
                blocks.append("\n".join(lines))

        return "\n\n".join(b for b in blocks if b.strip())

    def _build_messages(self, turn: Turn, prompts: dict, memories: str = "") -> list:
        # Most-stable content first (system + bio), newest content last, so the prefix
        # cache only re-evaluates the tail. PHASE 2 owns the prompt text in prompts.system.
        name = turn.bot_identity.name if turn.bot_identity else "cricket"
        base = prompts.get("system") or "You are %s, a character on a MUSH." % name
        system = base
        if turn.directives:
            system = "%s\n\n%s" % (base, turn.directives)
        messages = [{"role": "system", "content": system.strip()}]

        # Few-shot voice anchors as real turns (user prompt -> his actual pose). For an
        # instruction-tuned model this anchors STYLE far harder than describing it in the
        # system prompt -- it shows the model how Cricket specifically sounds, not just
        # "be unhinged". Absent/empty -> behaves exactly as before.
        for ex in prompts.get("fewshot") or []:
            u, a = ex.get("user", ""), ex.get("assistant", "")
            if u and a:
                messages.append({"role": "user", "content": u})
                messages.append({"role": "assistant", "content": a})

        # Live user message: memories block (changes only when the cast changes) first,
        # then prior history as its OWN block, then the live line called out explicitly.
        parts = []
        if memories.strip():
            parts.append("What you know:\n%s" % memories.strip())
        # History now includes the bot's own past replies (router feeds them back), so the
        # model sees the real back-and-forth and stops re-treading topics it already hit.
        history = ["%s: %s" % (line.speaker, line.text) for line in turn.context]
        if history:
            parts.append("Recent conversation (oldest first):\n" + "\n".join(history))
        if turn.mode == "rp":
            parts.append(
                "Compose %s's next pose, in character, reacting to the scene above." % name
            )
        else:
            # Chat: call out the latest line and tell the model to engage IT -- not riff on
            # the whole transcript, which is what makes him recycle old topics.
            if turn.text.strip():
                parts.append('%s just said: "%s"' % (turn.speaker, turn.text))
            parts.append(
                "Respond as %s to what was JUST said, in character. Engage the latest "
                "message directly; do not rehash earlier lines or repeat yourself." % name
            )
        messages.append({"role": "user", "content": "\n\n".join(parts)})
        return messages

    @staticmethod
    def _build_options(inference: dict) -> dict:
        """Map the profile inference block to Ollama options. backend 'cpu' forces all
        layers onto CPU (num_gpu=0); 'gpu' (or unset) lets Ollama use the GPU."""
        options: dict = {}
        for key in _PASSTHROUGH:
            val = inference.get(key)
            if val is not None:
                options[key] = val
        if inference.get("backend") == "cpu":
            options["num_gpu"] = 0
        return options

    async def summarize_scene(self, lines, cast=None) -> str:
        """Summarize a finished RP scene into a short memory note (an LLM call). Used by
        the memory accretion loop; see cricket.persona.base. Returns '' for an empty scene.
        """
        scene = "\n".join(
            "%s: %s" % (getattr(ln, "speaker", "") or "scene", getattr(ln, "text", ""))
            for ln in (lines or [])
        ).strip()
        if not scene:
            return ""
        who = ", ".join(cast) if cast else "unknown"
        doc = self._get_profile() or {}
        inference = doc.get("inference", {}) if isinstance(doc, dict) else {}
        options = self._build_options(inference)
        options["num_predict"] = 160  # a memory note is short
        messages = [
            {
                "role": "system",
                "content": "You write a terse memory note for the astromech droid Cricket. "
                "Factual third person, no roleplay, no shouting.",
            },
            {
                "role": "user",
                "content": "RP scene:\n%s\n\nIn 2-3 sentences, note what Cricket would "
                "remember: who was present (%s), what happened, and any slights or wins."
                % (scene, who),
            },
        ]
        text = await self._client.complete(
            messages, options=options, keep_alive=inference.get("keep_alive")
        )
        return (text or "").strip()
