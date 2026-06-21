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
    ) -> None:
        self._client = client
        # () -> active profile doc (dict) or None. Read on each turn so live edits apply.
        self._get_profile = profile_getter or (lambda: None)

    async def respond(self, turn: Turn) -> Union[Response, None]:
        doc = self._get_profile() or {}
        prompts = doc.get("prompts", {}) if isinstance(doc, dict) else {}
        inference = doc.get("inference", {}) if isinstance(doc, dict) else {}

        messages = self._build_messages(turn, prompts)
        options = self._build_options(inference)
        text = await self._client.complete(
            messages, options=options, keep_alive=inference.get("keep_alive")
        )
        text = (text or "").strip()
        if not text:
            return None
        action = "pose" if turn.mode == "rp" else "say"
        return Response(text=text, action=action)

    def _build_messages(self, turn: Turn, prompts: dict) -> list:
        # Most-stable content first (system + bio), newest content last, so the prefix
        # cache only re-evaluates the tail. PHASE 2 owns the prompt text in prompts.system.
        name = turn.bot_identity.name if turn.bot_identity else "cricket"
        base = prompts.get("system") or "You are %s, a character on a MUSH." % name
        system = base
        if turn.directives:
            system = "%s\n\n%s" % (base, turn.directives)
        messages = [{"role": "system", "content": system.strip()}]

        # Context oldest -> newest, then the triggering line, then a turn instruction.
        scene = []
        for line in turn.context:
            scene.append("%s: %s" % (line.speaker, line.text))
        if turn.text.strip():
            scene.append("%s: %s" % (turn.speaker, turn.text))
        if turn.mode == "rp":
            instruction = "Compose %s's next pose, in character." % name
        else:
            instruction = "Reply as %s, in character." % name
        user = "\n".join(scene + ["", instruction]) if scene else instruction
        messages.append({"role": "user", "content": user})
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
