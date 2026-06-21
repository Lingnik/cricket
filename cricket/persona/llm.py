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
    ) -> None:
        self._client = client
        # () -> active profile doc (dict) or None. Read on each turn so live edits apply.
        self._get_profile = profile_getter or (lambda: None)
        # Optional LoreStore: dossiers for the characters present are injected as a
        # memories block between the stable system prompt and the volatile scene.
        self._lore = lore

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
        room speakers are matched against known lore characters). Empty if no LoreStore."""
        if self._lore is None:
            return ""
        cast = []
        seen = set()
        for line in turn.context:
            spk = (line.speaker or "").strip()
            if spk and spk.lower() not in seen:
                seen.add(spk.lower())
                cast.append(spk)
        spk = (turn.speaker or "").strip()
        if spk and spk.lower() not in seen:
            cast.append(spk)
        return self._lore.retrieve(cast)

    def _build_messages(self, turn: Turn, prompts: dict, memories: str = "") -> list:
        # Most-stable content first (system + bio), newest content last, so the prefix
        # cache only re-evaluates the tail. PHASE 2 owns the prompt text in prompts.system.
        name = turn.bot_identity.name if turn.bot_identity else "cricket"
        base = prompts.get("system") or "You are %s, a character on a MUSH." % name
        system = base
        if turn.directives:
            system = "%s\n\n%s" % (base, turn.directives)
        messages = [{"role": "system", "content": system.strip()}]

        # User message: memories block (changes only when the cast changes) first, then
        # the scene oldest -> newest, then the triggering line and a turn instruction.
        parts = []
        if memories.strip():
            parts.append("What you know about who is here:\n%s" % memories.strip())
        scene = []
        for line in turn.context:
            scene.append("%s: %s" % (line.speaker, line.text))
        if turn.text.strip():
            scene.append("%s: %s" % (turn.speaker, turn.text))
        if scene:
            parts.append("\n".join(scene))
        if turn.mode == "rp":
            parts.append("Compose %s's next pose, in character." % name)
        else:
            parts.append("Reply as %s, in character." % name)
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
