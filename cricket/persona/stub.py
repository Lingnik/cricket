"""A no-model persona so the whole pipe runs end-to-end before an LLM exists.

It echoes chat lines, produces a canned pose for RP, and stays silent on empty chat
input -- enough to exercise routing, actions, the control socket, and memory.
"""

from __future__ import annotations

from typing import Union

from .base import Persona, Response, Turn


class StubPersona(Persona):
    async def respond(self, turn: Turn) -> Union[Response, None]:
        name = turn.bot_identity.name if turn.bot_identity else "cricket"

        if turn.mode == "rp":
            # Compose from the scene queue; demonstrate a pose.
            n = len(turn.context)
            return Response(
                text="%s considers the scene (%d line(s) queued)." % (name, n),
                action="pose",
            )

        # Chat mode: nothing to say to an empty line.
        if not turn.text.strip():
            return None

        return Response(text='%s heard: "%s"' % (name, turn.text), action="say")

    async def summarize_scene(self, lines, cast=None) -> str:
        """Trivial deterministic summary (no model) so the accretion loop is exercised."""
        if not lines:
            return ""
        first = (getattr(lines[0], "text", "") or "").strip()
        last = (getattr(lines[-1], "text", "") or "").strip()
        who = ", ".join(cast) if cast else "unknown"
        if first == last:
            return "Scene with %s: %s" % (who, first)
        return "Scene with %s: %s ... %s" % (who, first, last)
