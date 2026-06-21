"""LlmPersona: turns a Turn into a prompt, calls an InferenceClient, returns a Response.

The prompt assembly here is a deliberate PLACEHOLDER owned by phase 2 (the persona
session): system prompt, character sheet, context shaping, and sampling params are all
to be authored there. Phase 1 provides only the wiring so the seam is exercisable today
with any InferenceClient (e.g. EchoInferenceClient).
"""

from __future__ import annotations

from typing import Union

from .base import Persona, Response, Turn
from .inference import InferenceClient


class LlmPersona(Persona):
    def __init__(self, client: InferenceClient) -> None:
        self._client = client

    async def respond(self, turn: Turn) -> Union[Response, None]:
        messages = self._build_messages(turn)
        text = await self._client.complete(messages)
        if not text:
            return None
        action = "pose" if turn.mode == "rp" else "say"
        return Response(text=text, action=action)

    def _build_messages(self, turn: Turn) -> list:
        # PLACEHOLDER prompt assembly. Phase 2 owns the real system prompt / character
        # sheet / memory weaving; this is just enough to call the client end-to-end.
        name = turn.bot_identity.name if turn.bot_identity else "cricket"
        system = "You are %s. %s" % (name, turn.directives or "")
        messages = [{"role": "system", "content": system.strip()}]
        for line in turn.context:
            messages.append(
                {"role": "user", "content": "%s: %s" % (line.speaker, line.text)}
            )
        if turn.text.strip():
            messages.append(
                {"role": "user", "content": "%s: %s" % (turn.speaker, turn.text)}
            )
        return messages
