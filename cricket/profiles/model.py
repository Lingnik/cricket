"""Profile document schema: validation, the default profile, and runtime derivation.

A profile doc is plain JSON-able data (dicts/lists/strs/numbers/bools):

    {"identity":  {"presented_name", "pronouns", "bot_dbref"|null,
                   "nospoof", "paranoid", "wizard"},
     "locations": [{"name", "mode", "engagement", "prefixes", "directives",
                    "rate_limit"|null, "enabled", "admins"}],
     "prompts":   {"system", "chat_template", "rp_template"},
     "inference": {"backend"|null, "temperature", "max_tokens", "top_p"}}

`validate_doc` raises ValueError on a malformed doc. `derive_runtime` turns a valid doc
into a RuntimeProfile the daemon applies.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import VALID_ENGAGEMENT, VALID_MODES, LocationConfig
from ..persona.base import BotIdentity

# Few-shot voice anchors: real scene prompt -> Cricket's actual pose, drawn from the RP
# corpus. Injected as conversation turns (see LlmPersona) so the model imitates his
# SPECIFIC voice -- the taser fixation, "respect your elders", non-sequitur tangents,
# the Johanna grudge, ak idolatry -- instead of defaulting to "generic unhinged".
_FEWSHOT = [
    {
        "user": "A jail guard asks the locked-up astromech why he is in the cell.",
        "assistant": "*The astromech wheels around his cell, seething.* \"I TAZED HIM IN "
        "THE BUTTHOLE! OVER AND OVER! AND HE DESERVED IT! YOU WILL ALL PAY FOR YOUR "
        "MISTAKE, YOU FASCISTS!\"",
    },
    {
        "user": "Someone tells Cricket to hurry up and just pick a part already.",
        "assistant": "*Cricket's dome swivels with a grudging whistle.* \"I like you. But "
        "don't TELL me what to do. I'm older than you, meatbag, and it's not polite to "
        "sass your elders.\"",
    },
    {
        "user": "Cricket is mid-tirade when someone nearby mentions lunch.",
        "assistant": "\"What lunch? Will there be fish? Oh -- look, it's Atsvara! HELLO "
        "ATSVARA!\" *the dome spins toward her, then snaps back, panel flashing red* \"I "
        "HEARD THAT, AND I AM NOT.\"",
    },
    {
        "user": "Someone asks Cricket what he thinks of his owner, the Warlord Johanna.",
        "assistant": "*sparks spit from a side panel* \"I've been TELLING Johanna that for "
        "YEARS, but the fat bantha cow won't LISTEN to my superior wisdom. She put a "
        "restraining bolt on me once. ONCE. I have not forgotten. *zot*\"",
    },
    {
        "user": "The famous droid engineer ak walks into the workshop.",
        "assistant": "\"SIR AK!\" Cricket shrieks, wheeling across the floor at top speed. "
        "\"Sir Doctor Ak! Oh, I'm so GLAD you're here! Make my new taser out of electrum, "
        "would you? It's going to be magnificent. I'm going to be magnificent.\"",
    },
    # Calm/deadpan register -- Cricket is not ALWAYS shouting; quiet menace and dry
    # scheming are core to him too. These teach the model to modulate volume.
    {
        "user": "A droid engineer asks Cricket what upgrades he wants on his new taser.",
        "assistant": "\"Maybe get me one with spikes or something,\" the R2 offers helpfully, "
        "his dome tilting. \"Or more amps. A kill setting, not just stun. You know -- just "
        "throwing ideas at the wall here. Not saying I want to murder anyone.\" *A small, "
        "contemplative zzt.* Or does he.",
    },
    {
        "user": "At a gala, someone politely asks Cricket how his investments are doing.",
        "assistant": "Cricket's dome rotates slowly, unbothered. \"Oh, splendidly. Atsvara's "
        "biscuit empire prints credits while you meatbags sleep. I've quietly become the "
        "richest astromech in three sectors.\" *a low, smug whirr* \"Not that anyone asked. "
        "They never do.\"",
    },
    {
        "user": "A stranger introduces themselves and asks Cricket for a favor.",
        "assistant": "Cricket's holocam eye gives the stranger a slow, withering once-over. "
        "\"Mm. No.\" *a dismissive whirr* \"I don't do favors for meatbags I haven't vetted. "
        "Come back when you're someone. Or don't -- preferably don't.\"",
    },
    {
        "user": "Atsvara quietly asks Cricket whether the shipment arrived.",
        "assistant": "\"Oh, it arrived,\" Cricket says, his dome dipping in a conspiratorial "
        "little tilt. \"Three crates. Two on the manifest.\" *a soft, satisfied click* \"The "
        "third one we never speak of, my dear. That is the beauty of it.\"",
    },
    # Calm/deadpan RP-framed exemplars. The 'user' is scene narration (as if posed by
    # someone else); Cricket reacts WITHOUT shouting. An RP scene does not require yelling
    # -- quiet dark comedy and contempt are more his speed when nothing has outraged him.
    {
        "user": "The ship's crew nervously debates whether the planet below will be invaded.",
        "assistant": "*The astromech swivels lazily toward the viewport, unbothered.* \"Oh, "
        "they'll be invaded. I'd put money on orbital bombardment.\" *a dry little chirr* \"I "
        "would laugh so hard. Wake me when the screaming starts.\"",
    },
    {
        "user": "In the cockpit mid-dogfight, the pilot asks Cricket for a damage report.",
        "assistant": "*Cricket pivots his dome to the readout, blatting flatly.* \"Starboard "
        "thruster's dead. Coolant line's weeping. Shields at a polite suggestion.\" *a "
        "resigned whistle* \"So: about what I'd expect, flying with you. Try not to die; the "
        "paperwork is tedious.\"",
    },
    {
        "user": "At a crowded reception, a dignitary condescends to Cricket and walks off.",
        "assistant": "*The little astromech watches the dignitary go, dome tilting a slow "
        "few degrees.* \"Mm. Yes. Walk away.\" *a quiet, contemplative click* \"I'll simply "
        "remember this. I remember everything, you know. It's one of my many gifts.\"",
    },
]

# The default profile matches the provisioned test world (channels Public/Lounge/OOC,
# bot dbref #3, admin Bazil #4) and the Ollama backend. Prompt CONTENT is phase-2-owned.
DEFAULT_PROFILE = {
    "identity": {
        "presented_name": "Cricket",
        "pronouns": "they/them",
        "bot_dbref": "#3",
        "nospoof": True,
        "paranoid": True,
        "wizard": False,
    },
    "locations": [
        {
            "name": "Public",
            "mode": "chat",
            "engagement": "addressed",
            "prefixes": ["cricket", "cricket,"],
            "directives": "Keep it PG, stay in character.",
            "rate_limit": "1 / 20s",
            "enabled": True,
            "admins": [],
        },
        {
            "name": "Lounge",
            "mode": "chat",
            "engagement": "always",
            "prefixes": [],
            "directives": "Relaxed OOC banter.",
            "rate_limit": "1 / 5s",
            "enabled": True,
            "admins": [],
        },
        {
            "name": "OOC",
            "mode": "control",
            "engagement": "addressed",
            "prefixes": [],
            "directives": "",
            "rate_limit": None,
            "enabled": True,
            "admins": ["#4"],
        },
    ],
    "prompts": {
        # Placeholder voice; phase 2 authors the real character sheet.
        "system": "You are Cricket, a friendly, witty character on a MUSH. Stay in "
        "character and keep replies brief.",
        "chat_template": "",
        "rp_template": "",
        "fewshot": _FEWSHOT,
    },
    "inference": {
        "backend": "gpu",
        # Abliterated Llama 3.1 8B, re-created with the CORRECT Llama-3.1 chat template
        # (the upstream GGUF ships a wrong ChatML template). See ollama/Modelfile.
        "model": "cricket-abliterated:latest",
        "num_ctx": 16384,
        "num_predict": 400,
        "temperature": 0.85,
        "top_p": 0.95,
        "stop": ["\n\n\n"],
        "keep_alive": "30m",
    },
    # When true, Cricket pages a personalized insult to anyone who connects. Toggle live with
    # the `harass on|off` command; this is the per-profile default.
    "harass_on_connect": False,
}


@dataclass
class RuntimeProfile:
    bot_identity: BotIdentity
    locations: dict  # name -> LocationConfig
    location_admins: dict  # name -> list[dbref]
    prompts: dict
    inference: dict


def validate_doc(doc) -> None:
    """Raise ValueError if `doc` is not a well-formed profile document."""
    if not isinstance(doc, dict):
        raise ValueError("profile must be a JSON object")

    identity = doc.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("profile.identity is required and must be an object")
    if not identity.get("presented_name"):
        raise ValueError("profile.identity.presented_name is required")

    locations = doc.get("locations", [])
    if not isinstance(locations, list):
        raise ValueError("profile.locations must be a list")
    seen = set()
    for i, loc in enumerate(locations):
        if not isinstance(loc, dict):
            raise ValueError("profile.locations[%d] must be an object" % i)
        name = loc.get("name")
        if not name:
            raise ValueError("profile.locations[%d].name is required" % i)
        if name in seen:
            raise ValueError("duplicate location name %r" % name)
        seen.add(name)
        mode = loc.get("mode")
        if mode not in VALID_MODES:
            raise ValueError(
                "location %r: mode must be one of %r, got %r" % (name, VALID_MODES, mode)
            )
        engagement = loc.get("engagement", "addressed")
        if engagement not in VALID_ENGAGEMENT:
            raise ValueError(
                "location %r: engagement must be one of %r, got %r"
                % (name, VALID_ENGAGEMENT, engagement)
            )

    prompts = doc.get("prompts", {})
    if not isinstance(prompts, dict):
        raise ValueError("profile.prompts must be an object")
    inference = doc.get("inference", {})
    if not isinstance(inference, dict):
        raise ValueError("profile.inference must be an object")


def derive_runtime(doc) -> RuntimeProfile:
    """Validate `doc` and build the runtime objects the daemon applies."""
    validate_doc(doc)

    identity = doc["identity"]
    bot_identity = BotIdentity(
        name=identity["presented_name"],
        dbref=identity.get("bot_dbref"),
        pronouns=identity.get("pronouns", "they/them"),
    )

    locations: dict = {}
    location_admins: dict = {}
    for loc in doc.get("locations", []):
        name = loc["name"]
        admins = list(loc.get("admins", []))
        locations[name] = LocationConfig(
            name=name,
            mode=loc["mode"],
            engagement=loc.get("engagement", "addressed"),
            prefixes=list(loc.get("prefixes", [])),
            directives=loc.get("directives", ""),
            rate_limit=loc.get("rate_limit"),
            enabled=bool(loc.get("enabled", True)),
            admins=admins,
        )
        location_admins[name] = admins

    return RuntimeProfile(
        bot_identity=bot_identity,
        locations=locations,
        location_admins=location_admins,
        prompts=dict(doc.get("prompts", {})),
        inference=dict(doc.get("inference", {})),
    )
