"""SQLite-backed persistent store and the MemoryHandle the persona sees.

Schema (docs/DESIGN.md):
    actors(dbref PK, name, first_seen, last_seen, flags, notes)
    events(id, location, actor_dbref, kind, text, ts)   -- transcript / scene log
    memory(scope, scope_key, key, value, updated_ts)    -- persona-writable KV

Timestamps are Unix seconds. The persona never writes SQL: it uses MemoryHandle, whose
remember/recall map onto the "kv" scope of the memory table.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Union

def read_recent_events(path: Union[str, Path], n: int = 50) -> list:
    """Read the most recent events from a memory DB on its own short-lived connection.

    Safe to call from a thread other than the daemon's (the HTTP control panel uses it
    for /api/log). Returns [] if the database or table is not present yet.
    """
    try:
        conn = sqlite3.connect(str(path))
    except sqlite3.OperationalError:
        return []
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (int(n),)
        )
        rows = [dict(r) for r in cur.fetchall()]
        rows.reverse()  # oldest -> newest
        return rows
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS actors (
    dbref      TEXT PRIMARY KEY,
    name       TEXT,
    first_seen REAL,
    last_seen  REAL,
    flags      TEXT,
    notes      TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    location     TEXT,
    actor_dbref  TEXT,
    kind         TEXT,
    text         TEXT,
    ts           REAL
);
CREATE INDEX IF NOT EXISTS events_location_idx ON events(location, id);
CREATE TABLE IF NOT EXISTS memory (
    scope      TEXT,
    scope_key  TEXT,
    key        TEXT,
    value      TEXT,
    updated_ts REAL,
    PRIMARY KEY (scope, scope_key, key)
);
"""


class MemoryStore:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- actors ----------------------------------------------------------------
    def upsert_actor(self, dbref: str, name: str) -> None:
        now = time.time()
        cur = self._conn.execute(
            "SELECT dbref FROM actors WHERE dbref = ?", (dbref,)
        )
        if cur.fetchone() is None:
            self._conn.execute(
                "INSERT INTO actors (dbref, name, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?)",
                (dbref, name, now, now),
            )
        else:
            self._conn.execute(
                "UPDATE actors SET name = ?, last_seen = ? WHERE dbref = ?",
                (name, now, dbref),
            )
        self._conn.commit()

    def actor(self, dbref: str) -> Union[dict, None]:
        cur = self._conn.execute("SELECT * FROM actors WHERE dbref = ?", (dbref,))
        row = cur.fetchone()
        return dict(row) if row is not None else None

    # -- events ----------------------------------------------------------------
    def log_event(
        self,
        location: str,
        actor_dbref: Union[str, None],
        kind: str,
        text: str,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO events (location, actor_dbref, kind, text, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            (location, actor_dbref, kind, text, time.time()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def recent_events(self, location: str, n: int = 20) -> list:
        cur = self._conn.execute(
            "SELECT * FROM events WHERE location = ? ORDER BY id DESC LIMIT ?",
            (location, n),
        )
        rows = [dict(r) for r in cur.fetchall()]
        rows.reverse()  # oldest -> newest
        return rows

    # -- key/value memory ------------------------------------------------------
    def remember(self, scope: str, scope_key: str, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO memory (scope, scope_key, key, value, updated_ts) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(scope, scope_key, key) "
            "DO UPDATE SET value = excluded.value, updated_ts = excluded.updated_ts",
            (scope, scope_key, key, value, time.time()),
        )
        self._conn.commit()

    def recall(self, scope: str, scope_key: str, key: str) -> Union[str, None]:
        cur = self._conn.execute(
            "SELECT value FROM memory WHERE scope = ? AND scope_key = ? AND key = ?",
            (scope, scope_key, key),
        )
        row = cur.fetchone()
        return row["value"] if row is not None else None


class MemoryHandle:
    """The persona-facing view of the store. Passed on each Turn. The 3-argument
    remember/recall live in the "kv" scope; `scope` here is the scope_key (an actor
    dbref or a location name)."""

    KV = "kv"

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def actor(self, dbref: str) -> Union[dict, None]:
        return self._store.actor(dbref)

    def recent_events(self, location: str, n: int = 20) -> list:
        return self._store.recent_events(location, n)

    def remember(self, scope: str, key: str, value: str) -> None:
        self._store.remember(self.KV, scope, key, value)

    def recall(self, scope: str, key: str) -> Union[str, None]:
        return self._store.recall(self.KV, scope, key)
