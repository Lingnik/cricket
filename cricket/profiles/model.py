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
    },
    "inference": {
        "backend": "gpu",
        "model": "hf.co/mlabonne/Meta-Llama-3.1-8B-Instruct-abliterated-GGUF:Q5_K_M",
        "num_ctx": 16384,
        "num_predict": 400,
        "temperature": 0.85,
        "top_p": 0.95,
        "stop": ["\n\n\n"],
        "keep_alive": "30m",
    },
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
