"""The inference boundary: an abstract async client, an echo stub, and a concrete
Ollama client.

Persona code depends only on `InferenceClient`. `OllamaInferenceClient` talks to a local
Ollama server over plain localhost HTTP (stdlib urllib -- no third-party deps, no TLS).
See docs/INFERENCE_BACKEND.md for the measured backend spec.
"""

from __future__ import annotations

import abc
import asyncio
import json
import logging
import re
import urllib.request

log = logging.getLogger("cricket.inference")

# Some GGUF chat templates leak raw special tokens into the output (e.g. a trailing
# "<|im_end|>" or a malformed "|im_end|>"). Strip them defensively.
_SPECIAL_TOKEN = re.compile(
    r"<\|[^>]*?\|>"
    r"|<?\|?(?:im_end|im_start|eot_id|start_header_id|end_header_id"
    r"|begin_of_text|end_of_text)\|?>?"
)


def strip_special_tokens(text: str) -> str:
    """Remove leaked chat-template special tokens from generated text."""
    return _SPECIAL_TOKEN.sub("", text).strip()


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


class OllamaInferenceClient(InferenceClient):
    """Talks to a local Ollama server's /api/chat endpoint over plain HTTP.

    `options` is the Ollama options dict (num_ctx, num_predict, temperature, top_p, stop,
    and num_gpu=0 to force CPU). `keep_alive` holds the model/cache warm between turns.
    The blocking HTTP call runs in a thread so it never stalls the event loop.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 11434,
        model: str = "",
        timeout: float = 120.0,
    ) -> None:
        self.host = host
        self.port = port
        self.model = model
        self.timeout = timeout

    async def complete(self, messages: list, options=None, keep_alive=None, **_) -> str:
        body = {"model": self.model, "messages": messages, "stream": False}
        if keep_alive is not None:
            body["keep_alive"] = keep_alive
        if options:
            body["options"] = options
        url = "http://%s:%d/api/chat" % (self.host, self.port)
        data = json.dumps(body).encode("utf-8")
        resp = await asyncio.to_thread(self._post, url, data)
        self._log_timing(resp)
        return strip_special_tokens(resp.get("message", {}).get("content", ""))

    def _post(self, url: str, data: bytes) -> dict:
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    @staticmethod
    def _log_timing(resp: dict) -> None:
        count = resp.get("eval_count")
        dur = resp.get("eval_duration")  # nanoseconds
        if count and dur:
            secs = dur / 1e9
            log.info(
                "ollama: generated %d tok in %.2fs (%.1f tok/s)",
                count,
                secs,
                count / secs if secs else 0.0,
            )
