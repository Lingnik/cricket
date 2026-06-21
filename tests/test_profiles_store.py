import copy

import pytest

from cricket.profiles import DEFAULT_PROFILE, ConfigStore


def make_store(tmp_path):
    return ConfigStore(str(tmp_path / "config.sqlite3"))


def test_put_get_roundtrip(tmp_path):
    store = make_store(tmp_path)
    doc = copy.deepcopy(DEFAULT_PROFILE)
    store.put("alpha", doc)
    got = store.get("alpha")
    assert got == doc
    assert store.get("missing") is None


def test_list_profiles_sorted(tmp_path):
    store = make_store(tmp_path)
    store.put("beta", DEFAULT_PROFILE)
    store.put("alpha", DEFAULT_PROFILE)
    assert store.list_profiles() == ["alpha", "beta"]


def test_put_rejects_invalid_doc(tmp_path):
    store = make_store(tmp_path)
    bad = copy.deepcopy(DEFAULT_PROFILE)
    bad["locations"][0]["mode"] = "bogus"
    with pytest.raises(ValueError):
        store.put("bad", bad)
    assert store.list_profiles() == []


def test_put_rejects_missing_identity(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(ValueError):
        store.put("bad", {"locations": []})


def test_set_active_is_exclusive(tmp_path):
    store = make_store(tmp_path)
    store.put("a", DEFAULT_PROFILE)
    store.put("b", DEFAULT_PROFILE)
    store.set_active("a")
    assert store.active()[0] == "a"
    store.set_active("b")
    name, doc = store.active()
    assert name == "b"
    assert isinstance(doc, dict)


def test_set_active_unknown_raises(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(ValueError):
        store.set_active("nope")


def test_put_preserves_active_flag(tmp_path):
    store = make_store(tmp_path)
    store.put("a", DEFAULT_PROFILE)
    store.set_active("a")
    # Re-saving the active profile must not clear its active flag.
    edited = copy.deepcopy(DEFAULT_PROFILE)
    edited["identity"]["pronouns"] = "she/her"
    store.put("a", edited)
    assert store.active()[0] == "a"
    assert store.active()[1]["identity"]["pronouns"] == "she/her"


def test_delete(tmp_path):
    store = make_store(tmp_path)
    store.put("a", DEFAULT_PROFILE)
    store.delete("a")
    assert store.get("a") is None


def test_seed_default_if_empty(tmp_path):
    store = make_store(tmp_path)
    assert store.seed_default_if_empty(DEFAULT_PROFILE) is True
    assert store.active()[0] == "default"
    # Second call is a no-op because profiles already exist.
    assert store.seed_default_if_empty(DEFAULT_PROFILE) is False
    assert store.list_profiles() == ["default"]


def test_persists_across_instances(tmp_path):
    path = str(tmp_path / "config.sqlite3")
    s1 = ConfigStore(path)
    s1.put("a", DEFAULT_PROFILE)
    s1.set_active("a")
    s1.close()
    s2 = ConfigStore(path)
    assert s2.active()[0] == "a"
