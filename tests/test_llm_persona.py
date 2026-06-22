"""LlmPersona prompt assembly: few-shot voice anchors are injected as turns."""

import asyncio

from cricket.persona.base import BotIdentity, Turn
from cricket.persona.inference import InferenceClient
from cricket.persona.llm import LlmPersona


class RecordingClient(InferenceClient):
    """Captures the messages it is given and returns a fixed completion."""

    def __init__(self):
        self.messages = None

    async def complete(self, messages, **params):
        self.messages = messages
        return "ok"


def _turn(text="hello"):
    return Turn(
        mode="chat",
        location="Public",
        location_kind="channel",
        directives="",
        speaker="Bob",
        speaker_dbref="#5",
        text=text,
        context=[],
        bot_identity=BotIdentity(name="Cricket"),
        memory=None,
    )


def _run(persona, turn):
    return asyncio.run(persona.respond(turn))


def test_fewshot_injected_as_turns():
    client = RecordingClient()
    doc = {
        "prompts": {
            "system": "You are Cricket.",
            "fewshot": [
                {"user": "U1", "assistant": "A1"},
                {"user": "U2", "assistant": "A2"},
            ],
        }
    }
    persona = LlmPersona(client, lambda: doc)
    _run(persona, _turn())

    roles = [(m["role"], m["content"]) for m in client.messages]
    # system, then the example pairs as real turns, then the live user message
    assert roles[0][0] == "system"
    assert ("user", "U1") in roles and ("assistant", "A1") in roles
    assert ("user", "U2") in roles and ("assistant", "A2") in roles
    assert roles[1] == ("user", "U1")
    assert roles[2] == ("assistant", "A1")
    assert roles[3] == ("user", "U2")
    assert roles[4] == ("assistant", "A2")
    assert client.messages[-1]["role"] == "user"  # the live turn is last


def test_no_fewshot_is_unchanged():
    client = RecordingClient()
    doc = {"prompts": {"system": "You are Cricket."}}
    persona = LlmPersona(client, lambda: doc)
    _run(persona, _turn())
    roles = [m["role"] for m in client.messages]
    assert roles == ["system", "user"]


def test_fewshot_skips_incomplete_pairs():
    client = RecordingClient()
    doc = {"prompts": {"system": "s", "fewshot": [{"user": "U1"}, {"assistant": "A2"}]}}
    persona = LlmPersona(client, lambda: doc)
    _run(persona, _turn())
    assert [m["role"] for m in client.messages] == ["system", "user"]


class TwoCallClient(InferenceClient):
    """Returns a plan on the first call, the final line on the second."""

    def __init__(self):
        self.calls = []

    async def complete(self, messages, **params):
        self.calls.append(messages)
        if len(self.calls) == 1:
            return "- react to Bob\n- threaten with the taser"
        return "FINAL LINE"


def test_thinking_runs_planning_pass_then_injects_plan():
    client = TwoCallClient()
    doc = {"prompts": {"system": "s"}, "inference": {"thinking": True}}
    persona = LlmPersona(client, lambda: doc)
    resp = _run(persona, _turn("oi droid"))
    # Two completions: the hidden planning pass, then the real reply.
    assert len(client.calls) == 2
    assert "privately PLAN" in client.calls[0][-1]["content"]
    final_user = client.calls[1][-1]["content"]
    assert "Your private plan" in final_user and "threaten with the taser" in final_user
    assert resp.text == "FINAL LINE"   # the plan is never the output


def test_thinking_off_by_default_single_pass():
    client = TwoCallClient()
    persona = LlmPersona(client, lambda: {"prompts": {"system": "s"}})
    _run(persona, _turn())
    assert len(client.calls) == 1
    assert "Your private plan" not in client.calls[0][-1]["content"]


class _CharterLore:
    def self_history(self):
        return ""

    def rp_charter(self):
        return "RP-RULES-MARKER"

    def mentioned(self, text, max_names=4):
        return []

    def retrieve(self, cast, scope=None, max_chars=4000):
        return ""


def _rp_turn():
    from cricket.persona.base import ContextLine
    return Turn(
        mode="rp", location="#0", location_kind="room", directives="", speaker="",
        speaker_dbref="", text="", context=[ContextLine("scene", None, "pose", "x happens")],
        bot_identity=BotIdentity(name="Cricket"), memory=None,
    )


class _OwnLore:
    def self_history(self):
        return ""

    def rp_charter(self):
        return ""

    def retrieve(self, cast, scope=None, max_chars=4000):
        return ""

    def mentioned(self, text, max_names=4):
        return ["Tindomiel"] if "Tindomiel" in text else []


def test_do_not_puppet_set_from_scene_ownership():
    from cricket.persona.base import ContextLine
    c = RecordingClient()
    ctx = [
        ContextLine("Johanna", "#4", "pose", "smiles coldly."),       # her own character
        ContextLine("Johanna", "#4", "emit", "Tindomiel giggles."),   # an NPC she puppets
        ContextLine("scene", None, "pose", "The hall is dim."),       # no dbref -> not a poser
    ]
    turn = Turn(mode="rp", location="#0", location_kind="room", directives="", speaker="",
                speaker_dbref="", text="", context=ctx, bot_identity=BotIdentity(name="Cricket"),
                memory=None)
    _run(LlmPersona(c, lambda: {"prompts": {"system": "s"}}, lore=_OwnLore()), turn)
    msg = c.messages[-1]["content"]
    assert "belong to other players" in msg
    assert "Johanna" in msg and "Tindomiel" in msg  # her char + the NPC she posed


def test_claimed_field_merges_into_do_not_puppet():
    c = RecordingClient()
    turn = Turn(mode="rp", location="#0", location_kind="room", directives="", speaker="",
                speaker_dbref="", text="", context=[], bot_identity=BotIdentity(name="Cricket"),
                memory=None, claimed=["Tindomiel", "Cricket"])
    _run(LlmPersona(c, lambda: {"prompts": {"system": "s"}}, lore=_OwnLore()), turn)
    msg = c.messages[-1]["content"]
    assert "belong to other players" in msg
    assert "Tindomiel" in msg          # distillation-supplied name
    assert "Cricket" not in msg.split("belong to other players")[1][:60]  # bot filtered out


def test_speaker_name_resolved_to_canonical_for_dossier():
    # A poser arrives as "Jessalyn" but her dossier is keyed "Jessalyn Valios". The gazetteer must
    # resolve the raw SPEAKER name (not just text mentions) so the present character's dossier
    # injects -- without this, dossiers for present characters are silently missed (grounding drift).
    from cricket.persona.base import ContextLine

    class _GazLore:
        def self_history(self):
            return ""

        def rp_charter(self):
            return ""

        def mentioned(self, text, max_names=4):
            return ["Jessalyn Valios"] if "jessalyn" in (text or "").lower() else []

        def retrieve(self, cast, scope=None, max_chars=4000):
            return "JESSALYN-DOSSIER" if "Jessalyn Valios" in cast else ""

        def dossier(self, name):
            return name == "Jessalyn Valios"

    c = RecordingClient()
    turn = Turn(mode="rp", location="#0", location_kind="room", directives="", speaker="",
                speaker_dbref="", text="",
                context=[ContextLine("Jessalyn", "#7", "pose", "grins at the droid.")],
                bot_identity=BotIdentity(name="Cricket"), memory=None)
    _run(LlmPersona(c, lambda: {"prompts": {"system": "s"}}, lore=_GazLore()), turn)
    assert "JESSALYN-DOSSIER" in c.messages[-1]["content"]  # canonical dossier reached the prompt


def test_clean_output_format_hygiene():
    from cricket.persona.llm import _clean_output
    # leaked speech-verb/name prefix the wrapper re-adds is dropped
    assert _clean_output('Cricket says, "Hi there"', "chat") == "Hi there"
    assert _clean_output("Cricket: hello", "chat") == "hello"
    # asterisk stage-directions removed (it is @emit prose, not a script)
    assert _clean_output('*The dome dips.* "Mine."', "rp") == 'The dome dips. "Mine."'
    # channel speech: a wrapping quote pair would nest inside `X says, "..."`
    assert _clean_output('"Johanna is my owner"', "chat") == "Johanna is my owner"
    # a single dangling close-quote reads as broken
    assert _clean_output('He says hi"', "chat") == "He says hi"
    # an unclosed opener gets closed at the end
    assert _clean_output('The dome dips. "You are mine, meatbag', "rp") == 'The dome dips. "You are mine, meatbag"'
    # valid third-person @emit openings are PRESERVED (not mistaken for a name prefix)
    assert _clean_output("Cricket's dome swivels in disdain.", "rp") == "Cricket's dome swivels in disdain."
    assert _clean_output("Cricket whirs angrily at the meatbag.", "rp") == "Cricket whirs angrily at the meatbag."
    # the cleanup bug: an asterisk beat wedged between two quotes must become its own sentence,
    # not a lowercase fragment with no punctuation
    assert _clean_output('"Still burning?" *the pincer twitches* "I am watching."', "rp") \
        == '"Still burning?" The pincer twitches. "I am watching."'
    # leaked raw @emit command verb (some RP tunes echo it) is stripped
    assert _clean_output("@emit\nThe dome swivels.", "rp") == "The dome swivels."
    # truncated-at-token-cap pose trims back to the last complete sentence
    assert _clean_output('He zots once. "Fine," he grumbles. Then he wheels off toward the', "rp") \
        == 'He zots once. "Fine," he grumbles.'


def test_to_mush_markup_restores_rt():
    from cricket.persona.llm import _to_mush_markup
    # PennMUSH delivered the players' %r/%t as literal newlines/tabs; we render them back so the
    # model sees -- and learns to emit -- MUSH markup.
    assert _to_mush_markup("a.\n\n\tb") == "a.%r%r%tb"
    assert _to_mush_markup("x\r\ny") == "x%ry"
    assert _to_mush_markup("no breaks") == "no breaks"
    assert _to_mush_markup("") == ""


def test_respond_applies_cleanup():
    class DirtyClient(InferenceClient):
        async def complete(self, messages, **params):
            return 'Cricket says, "*beeps* You absolute fool"'

    resp = _run(LlmPersona(DirtyClient(), lambda: {"prompts": {"system": "s"}}), _turn())
    # prefix + nesting quotes gone; the *beeps* action beat is promoted to a clean sentence
    assert resp.text == "Beeps. You absolute fool"


class _Block:
    """Minimal completed pose-block: distill_block reads .text and .speaker."""

    def __init__(self, speaker, text):
        self.speaker = speaker
        self.text = text


class _DistillClient(InferenceClient):
    """Returns a fixed distillation output (captures the prompt for inspection)."""

    def __init__(self, out):
        self._out = out
        self.messages = None

    async def complete(self, messages, **params):
        self.messages = messages
        return self._out


def _distill(out, speaker="Johanna", text="storms in"):
    client = _DistillClient(out)
    persona = LlmPersona(client, lambda: {"prompts": {"system": "s"}})
    result = asyncio.run(persona.distill_block(_Block(speaker, text), bot_name="Cricket"))
    return result, client


def test_distill_strips_preamble_and_parses_actors():
    # The weak 8B leaks framing ("Scene ledger updated:") as its own first line, with the
    # real note following. The label-keyed parser must skip the preamble line and keep the note.
    out = (
        "Scene ledger updated:\n"
        "NOTE: Johanna storms in demanding three million credits | "
        "Cricket's read: she is bluffing, the credits are long spent\n"
        "ACTORS: Johanna"
    )
    result, _ = _distill(out)
    assert result["ledger"].startswith("Johanna storms in demanding three million credits")
    assert "Scene ledger updated" not in result["ledger"]
    assert "Cricket's read" in result["ledger"]
    assert result["actors"] == ["Johanna"]


def test_distill_strips_inline_here_is_preamble():
    # Preamble and note share one line, no NOTE label -> the preamble regex peels the framing.
    out = (
        "Here is the updated scene ledger: Zeak thumbs his blaster and offers to crack Cricket open\n"
        "ACTORS: Zeak"
    )
    result, _ = _distill(out, speaker="Zeak", text="thumbs blaster")
    assert result["ledger"].startswith("Zeak thumbs his blaster")
    assert "Here is" not in result["ledger"] and "ledger" not in result["ledger"].lower()
    assert result["actors"] == ["Zeak"]


def test_distill_strips_leading_table_pipe_preamble():
    # The observed '| Scene ledger updated:' leak: a markdown-table pipe in front of framing.
    out = (
        "| Scene ledger updated:\n"
        "NOTE: Jessalyn grins and asks Cricket for his side of the story\n"
        "ACTORS: Jessalyn"
    )
    result, _ = _distill(out, speaker="Jessalyn", text="grins")
    assert result["ledger"].startswith("Jessalyn grins")
    assert "ledger" not in result["ledger"].lower()
    assert result["actors"] == ["Jessalyn"]


def test_distill_actors_none_yields_empty_list():
    out = "NOTE: The hall lights flicker; no one moves\nACTORS: none"
    result, _ = _distill(out, speaker="scene", text="lights flicker")
    assert result["ledger"].startswith("The hall lights flicker")
    assert result["actors"] == []


def test_distill_prompt_forbids_preamble():
    # The prompt must forcefully forbid framing and demand the NOTE/ACTORS contract.
    _, client = _distill("NOTE: x | Cricket's read: y\nACTORS: none")
    user = client.messages[-1]["content"]
    system = client.messages[0]["content"]
    assert "NOTE:" in user and "ACTORS:" in user
    assert "no preamble" in system.lower()
    assert "Scene ledger updated" in user  # explicitly named as a thing NOT to emit


def test_rp_charter_injected_on_rp_only():
    c = RecordingClient()
    LlmPersona(c, lambda: {"prompts": {"system": "s"}}, lore=_CharterLore())
    _run(LlmPersona(c, lambda: {"prompts": {"system": "s"}}, lore=_CharterLore()), _rp_turn())
    assert "RP-RULES-MARKER" in c.messages[0]["content"]  # system block, RP turn
    c2 = RecordingClient()
    _run(LlmPersona(c2, lambda: {"prompts": {"system": "s"}}, lore=_CharterLore()), _turn())
    assert "RP-RULES-MARKER" not in c2.messages[0]["content"]  # chat turn -> no charter
