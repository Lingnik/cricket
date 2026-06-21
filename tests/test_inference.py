import asyncio
import json
from unittest import mock

from cricket.persona.base import BotIdentity, Turn
from cricket.persona.inference import (
    EchoInferenceClient,
    OllamaInferenceClient,
    strip_special_tokens,
)
from cricket.persona.llm import LlmPersona


def test_strip_special_tokens_removes_template_tokens_and_html():
    assert strip_special_tokens("hello <|im_end|> world") == "hello  world"
    assert strip_special_tokens("a trailing |im_end|>") == "a trailing"
    assert "<br" not in strip_special_tokens("line one <br/> line two")


def test_strip_special_tokens_truncates_role_break():
    # The model breaks character on a new line with a role marker; cut it off.
    out = strip_special_tokens(
        "all his glory!\nassistant Let me know if you need changes."
    )
    assert out == "all his glory!"


def test_strip_special_tokens_keeps_role_word_in_dialogue():
    # "assistant" inside a sentence (not line-anchored) must NOT truncate.
    text = '"Fetch my assistant, you fool," Cricket snaps.'
    assert strip_special_tokens(text) == text


class _FakeResp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_ollama_builds_body_and_extracts_content():
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResp(
            json.dumps(
                {
                    "message": {"content": "hi there"},
                    "eval_count": 10,
                    "eval_duration": 1_000_000_000,
                }
            ).encode("utf-8")
        )

    client = OllamaInferenceClient(model="m1")
    with mock.patch(
        "cricket.persona.inference.urllib.request.urlopen", fake_urlopen
    ):
        out = asyncio.run(
            client.complete(
                [{"role": "user", "content": "yo"}],
                options={"num_ctx": 16384, "num_gpu": 0},
                keep_alive="30m",
            )
        )

    assert out == "hi there"
    assert captured["url"].endswith("/api/chat")
    assert captured["body"]["model"] == "m1"
    assert captured["body"]["stream"] is False
    assert captured["body"]["keep_alive"] == "30m"
    assert captured["body"]["options"]["num_gpu"] == 0


def test_llm_options_cpu_sets_num_gpu_zero():
    opts = LlmPersona._build_options(
        {"backend": "cpu", "num_ctx": 8192, "temperature": 0.8}
    )
    assert opts["num_gpu"] == 0
    assert opts["num_ctx"] == 8192
    assert opts["temperature"] == 0.8


def test_llm_options_gpu_omits_num_gpu():
    opts = LlmPersona._build_options({"backend": "gpu", "top_p": 0.95})
    assert "num_gpu" not in opts
    assert opts["top_p"] == 0.95


def test_llm_respond_uses_profile_and_returns_response():
    profile = {
        "prompts": {"system": "You are Cricket."},
        "inference": {"backend": "gpu", "temperature": 0.85},
    }
    persona = LlmPersona(EchoInferenceClient(), lambda: profile)
    turn = Turn(
        mode="chat",
        location="Public",
        location_kind="channel",
        directives="Keep it PG.",
        speaker="Bob",
        speaker_dbref="#5",
        text="hello cricket",
        context=[],
        bot_identity=BotIdentity(name="Cricket"),
    )
    resp = asyncio.run(persona.respond(turn))
    assert resp is not None
    assert resp.action == "say"
    assert "hello cricket" in resp.text  # echo client reflects the user content
