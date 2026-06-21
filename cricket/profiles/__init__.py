"""Persona profiles: the live-editable behavioral configuration.

A profile bundles the bot identity, per-location engagement/directives, the persona
prompts, and inference params. Profiles live in the committed config DB and are edited at
runtime over HTTP. `derive_runtime` turns a profile doc into the runtime objects the rest
of the program consumes (BotIdentity + LocationConfigs + per-location admin grants).
"""

from .model import DEFAULT_PROFILE, RuntimeProfile, derive_runtime, validate_doc
from .store import ConfigStore

__all__ = [
    "ConfigStore",
    "DEFAULT_PROFILE",
    "RuntimeProfile",
    "derive_runtime",
    "validate_doc",
]
