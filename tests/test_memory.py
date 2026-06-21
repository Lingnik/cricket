from cricket.memory.store import MemoryHandle, MemoryStore


def test_actor_upsert_and_fetch(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    assert store.actor("#1") is None
    store.upsert_actor("#1", "Bob")
    rec = store.actor("#1")
    assert rec["name"] == "Bob"
    assert rec["first_seen"] is not None
    assert rec["last_seen"] is not None
    # Second upsert updates name/last_seen, keeps the row.
    store.upsert_actor("#1", "Bobby")
    assert store.actor("#1")["name"] == "Bobby"
    store.close()


def test_events_log_and_recent_order(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    store.log_event("Public", "#1", "say", "first")
    store.log_event("Public", "#1", "say", "second")
    store.log_event("Other", "#2", "say", "elsewhere")
    recent = store.recent_events("Public", 10)
    assert [e["text"] for e in recent] == ["first", "second"]  # oldest -> newest
    assert store.recent_events("Other", 10)[0]["text"] == "elsewhere"
    store.close()


def test_memory_kv_roundtrip(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    assert store.recall("kv", "#1", "mood") is None
    store.remember("kv", "#1", "mood", "happy")
    assert store.recall("kv", "#1", "mood") == "happy"
    # Upsert overwrites.
    store.remember("kv", "#1", "mood", "grumpy")
    assert store.recall("kv", "#1", "mood") == "grumpy"
    store.close()


def test_memory_handle_maps_to_kv_scope(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    handle = MemoryHandle(store)
    handle.remember("#7", "trust", "high")
    assert handle.recall("#7", "trust") == "high"
    # The handle's 3-arg form lands in the "kv" scope of the store.
    assert store.recall("kv", "#7", "trust") == "high"
    store.upsert_actor("#7", "Cara")
    assert handle.actor("#7")["name"] == "Cara"
    store.close()


def test_persists_across_reopen(tmp_path):
    path = tmp_path / "m.sqlite3"
    store = MemoryStore(path)
    store.remember("kv", "#1", "k", "v")
    store.close()
    reopened = MemoryStore(path)
    assert reopened.recall("kv", "#1", "k") == "v"
    reopened.close()
