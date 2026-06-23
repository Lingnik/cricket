"""SQLite-backed persistent store and the MemoryHandle the persona sees.

Schema (docs/DESIGN.md):
    actors(dbref PK, name, first_seen, last_seen, flags, notes)
    events(id, location, actor_dbref, kind, text, ts)   -- transcript / scene log
    memory(scope, scope_key, key, value, updated_ts)    -- persona-writable KV

Timestamps are Unix seconds. The persona never writes SQL: it uses MemoryHandle, whose
remember/recall map onto the "kv" scope of the memory table.
"""

from __future__ import annotations

import json
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
    ts           REAL,
    masked       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS events_location_idx ON events(location, id);
CREATE TABLE IF NOT EXISTS memory (
    scope      TEXT,
    scope_key  TEXT,
    key        TEXT,
    value      TEXT,
    updated_ts REAL,
    masked     INTEGER NOT NULL DEFAULT 0,
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
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """Add the `masked` soft-redact column to pre-existing tables (we no longer swap DBs, so
        the one live DB is migrated in place)."""
        for table in ("events", "memory"):
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(%s)" % table)}
            if "masked" not in cols:
                self._conn.execute(
                    "ALTER TABLE %s ADD COLUMN masked INTEGER NOT NULL DEFAULT 0" % table)

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
        # Context/active read: masked (redacted) events are excluded -- they stay in the audit
        # trail but never re-enter anything Cricket sees.
        cur = self._conn.execute(
            "SELECT * FROM events WHERE location = ? AND masked = 0 ORDER BY id DESC LIMIT ?",
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
        # Masked memory is redacted from the context window -- recall skips it.
        cur = self._conn.execute(
            "SELECT value FROM memory WHERE scope = ? AND scope_key = ? AND key = ? AND masked = 0",
            (scope, scope_key, key),
        )
        row = cur.fetchone()
        return row["value"] if row is not None else None

    # -- standing directives ---------------------------------------------------
    # Dry, rule-oriented writing rules distilled from OOC feedback. Persistent (survive scenes and
    # restarts), sourced, injected into every future pose. Masking removes one; clear masks all.
    def save_directive(self, rule: str, source: str) -> None:
        import hashlib
        rule = (rule or "").strip()
        if not rule:
            return
        key = hashlib.sha1(rule.lower().encode("utf-8")).hexdigest()[:16]
        self.remember("directive", "global", key,
                      json.dumps({"rule": rule, "source": source or "?", "ts": round(time.time(), 3)}))

    def list_directives(self) -> list:
        rows = self._conn.execute(
            "SELECT value FROM memory WHERE scope='directive' AND masked=0 ORDER BY updated_ts"
        ).fetchall()
        out = []
        for r in rows:
            try:
                out.append(json.loads(r["value"]))
            except (ValueError, TypeError):
                pass
        return out

    def clear_directives(self) -> int:
        cur = self._conn.execute(
            "UPDATE memory SET masked=1 WHERE scope='directive' AND masked=0")
        self._conn.commit()
        return cur.rowcount

    # -- scene memory ----------------------------------------------------------
    # A finished RP scene is summarized (by the persona) and persisted per room so the
    # next scene there can recall what happened. Stored in the "scene" memory scope keyed
    # by room; the latest summary per room wins.
    def save_scene_summary(self, room: str, cast, summary: str) -> None:
        self.remember("scene", room, "summary", summary)
        self.remember("scene", room, "cast", ", ".join(cast or []))

    def recall_scene_summary(self, room: str) -> Union[str, None]:
        return self.recall("scene", room, "summary")

    # -- inspection + surgery (excising induced or test memories) ---------------
    def memory_digest(self) -> dict:
        """Compact overview for the control API / web panel: counts + the scene summaries
        (each flagged with its masked state)."""
        ev = self._conn.execute("SELECT count(*) AS n FROM events").fetchone()["n"]
        masked_ev = self._conn.execute("SELECT count(*) AS n FROM events WHERE masked = 1").fetchone()["n"]
        mem = self._conn.execute("SELECT count(*) AS n FROM memory").fetchone()["n"]
        scenes = [
            {"room": r["scope_key"], "summary": r["value"], "updated_ts": r["updated_ts"],
             "masked": bool(r["masked"])}
            for r in self._conn.execute(
                "SELECT scope_key, value, updated_ts, masked FROM memory "
                "WHERE scope = 'scene' AND key = 'summary' ORDER BY updated_ts DESC"
            ).fetchall()
        ]
        return {"events": ev, "events_masked": masked_ev, "memory_rows": mem, "scenes": scenes}

    # -- audit trail + masking (soft-redact from context; keep the paper trail) --
    def list_events(self, location=None, limit: int = 200, include_masked: bool = True) -> list:
        """The audit trail: received messages/commands, newest first. include_masked=False hides
        already-redacted rows. Each row carries its `masked` flag for the audit view."""
        where, params = [], []
        if location:
            where.append("location = ?")
            params.append(location)
        if not include_masked:
            where.append("masked = 0")
        sql = "SELECT id, location, actor_dbref, kind, text, ts, masked FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def mask_event(self, event_id: int, masked: bool = True) -> int:
        """Soft-redact (or restore) a single received message: it stays in the audit trail but is
        excluded from anything Cricket sees. Returns rows affected."""
        cur = self._conn.execute(
            "UPDATE events SET masked = ? WHERE id = ?", (1 if masked else 0, int(event_id)))
        self._conn.commit()
        return cur.rowcount

    def mask_memory(self, scope: str, scope_key: str, key=None, masked: bool = True) -> int:
        """Soft-redact (or restore) memory rows (e.g. a scene summary): masked memory is skipped by
        recall, so it never re-enters the context window. Returns rows affected."""
        m = 1 if masked else 0
        if key is None:
            cur = self._conn.execute(
                "UPDATE memory SET masked = ? WHERE scope = ? AND scope_key = ?", (m, scope, scope_key))
        else:
            cur = self._conn.execute(
                "UPDATE memory SET masked = ? WHERE scope = ? AND scope_key = ? AND key = ?",
                (m, scope, scope_key, key))
        self._conn.commit()
        return cur.rowcount

    def list_memory(self) -> list:
        """All key/value memory rows (scene summaries etc.), newest first -- for inspection."""
        cur = self._conn.execute(
            "SELECT scope, scope_key, key, value, updated_ts FROM memory ORDER BY updated_ts DESC"
        )
        return [dict(r) for r in cur.fetchall()]

    def delete_memory(self, scope: str, scope_key: str, key=None) -> int:
        """Delete memory rows by scope + scope_key (+ optional key). Returns rows removed."""
        if key is None:
            cur = self._conn.execute(
                "DELETE FROM memory WHERE scope = ? AND scope_key = ?", (scope, scope_key))
        else:
            cur = self._conn.execute(
                "DELETE FROM memory WHERE scope = ? AND scope_key = ? AND key = ?",
                (scope, scope_key, key))
        self._conn.commit()
        return cur.rowcount

    def purge_location(self, location: str) -> int:
        """Delete all logged events for a location/room. Returns rows removed."""
        cur = self._conn.execute("DELETE FROM events WHERE location = ?", (location,))
        self._conn.commit()
        return cur.rowcount

    def purge_scene(self, room: str) -> dict:
        """Excise a room's scene entirely -- its scene summary/cast memory AND its logged events.
        The 'brain surgery' for an induced or unwanted scene. Returns the counts removed."""
        mem = self.delete_memory("scene", room)
        ev = self.purge_location(room)
        return {"room": room, "memory_rows_removed": mem, "events_removed": ev}


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
