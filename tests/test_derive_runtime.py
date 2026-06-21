import copy

import pytest

from cricket.config import LocationConfig
from cricket.persona.base import BotIdentity
from cricket.profiles import DEFAULT_PROFILE, derive_runtime
from cricket.profiles.model import validate_doc


def test_derive_identity():
    rt = derive_runtime(DEFAULT_PROFILE)
    assert isinstance(rt.bot_identity, BotIdentity)
    assert rt.bot_identity.name == "Cricket"
    assert rt.bot_identity.pronouns == "they/them"


def test_derive_locations_and_admins():
    doc = copy.deepcopy(DEFAULT_PROFILE)
    doc["locations"][0]["admins"] = ["#10", "#11"]
    rt = derive_runtime(doc)
    assert set(rt.locations) == {"Public", "Lounge", "OOC"}
    public = rt.locations["Public"]
    assert isinstance(public, LocationConfig)
    assert public.mode == "chat"
    assert public.engagement == "addressed"
    assert "cricket," in public.prefixes
    assert rt.locations["Lounge"].engagement == "always"
    assert rt.locations["OOC"].mode == "control"
    assert rt.location_admins["Public"] == ["#10", "#11"]
    assert rt.location_admins["OOC"] == ["#4"]


def test_derive_carries_prompts_and_inference():
    rt = derive_runtime(DEFAULT_PROFILE)
    assert "system" in rt.prompts
    assert rt.inference["temperature"] == 0.85
    assert rt.inference["backend"] == "gpu"


def test_invalid_mode_raises():
    doc = copy.deepcopy(DEFAULT_PROFILE)
    doc["locations"][0]["mode"] = "bogus"
    with pytest.raises(ValueError):
        derive_runtime(doc)


def test_invalid_engagement_raises():
    doc = copy.deepcopy(DEFAULT_PROFILE)
    doc["locations"][0]["engagement"] = "sometimes"
    with pytest.raises(ValueError):
        derive_runtime(doc)


def test_missing_identity_raises():
    with pytest.raises(ValueError):
        derive_runtime({"locations": []})


def test_duplicate_location_name_raises():
    doc = copy.deepcopy(DEFAULT_PROFILE)
    doc["locations"][1]["name"] = "Public"
    with pytest.raises(ValueError):
        validate_doc(doc)
