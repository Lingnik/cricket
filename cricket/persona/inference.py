"""The inference boundary. The LLM backend is undecided, so this defines only an
abstract async client plus an echo stub. No model, no transformers, no HTTP, no model
paths live here -- a concrete backend is wired in a later phase behind this interface.
"""

from __future__ import annotations

import abc


class InferenceClient(abc.ABC):
    """Abstract text-completion client. A concrete implementation (local server,
    hosted API, ...) is chosen later; persona code depends only on this."""

    @abc.abstractmethod
    async def complete(self, messages: list, **params) -> str:
        """Given chat-style messages (dicts with 'role' and 'content'), return the
        assistant's text completion. `params` carries sampling settings (temperature,
        max tokens, ...) that the persona supplies."""
        raise NotImplementedError


class EchoInferenceClient(InferenceClient):
    """Returns a canned completion derived from the last user message. Lets the rest
    of the system be exercised with no model present."""

    async def complete(self, messages: list, **params) -> str:
        last_user = ""
        for msg in messages:
            if msg.get("role") == "user":
                last_user = msg.get("content", "")
        return "[echo] %s" % last_user
