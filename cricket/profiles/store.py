"""The committed config DB: persona profiles, stored as JSON docs in SQLite.

    profiles(name PK, is_active, doc TEXT, updated_ts)

At most one row has is_active=1. Every method opens its own short-lived connection, so
the store is safe to call from any thread (the daemon's loop and the HTTP thread both
touch it). WAL mode is set so a reader on one connection sees a committed write from
another immediately. `doc` is validated on write via cricket.profiles.model.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Union

from .model import validate_doc

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    name       TEXT PRIMARY KEY,
    is_active  INTEGER NOT NULL DEFAULT 0,
    doc        TEXT NOT NULL,
    updated_ts REAL
);
"""


class ConfigStore:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # An in-memory database lives only as long as its connection, so it must be kept
        # open; a file database opens a fresh connection per call (thread-safe).
        self._shared = sqlite3.connect(self.path) if self.path == ":memory:" else None
        with self._session() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _session(self):
        """Yield a connection, commit on success, and close it (unless shared)."""
        if self._shared is not None:
            conn = self._shared
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            return
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def close(self) -> None:
        if self._shared is not None:
            self._shared.close()

    # -- reads -----------------------------------------------------------------
    def list_profiles(self) -> list:
        with self._session() as conn:
            rows = conn.execute("SELECT name FROM profiles ORDER BY name").fetchall()
            return [r[0] for r in rows]

    def get(self, name: str) -> Union[dict, None]:
        with self._session() as conn:
            row = conn.execute(
                "SELECT doc FROM profiles WHERE name = ?", (name,)
            ).fetchone()
            return json.loads(row[0]) if row is not None else None

    def active(self):
        """Return (name, doc) of the active profile, or None."""
        with self._session() as conn:
            row = conn.execute(
                "SELECT name, doc FROM profiles WHERE is_active = 1 LIMIT 1"
            ).fetchone()
            return (row[0], json.loads(row[1])) if row is not None else None

    # -- writes ----------------------------------------------------------------
    def put(self, name: str, doc: dict) -> None:
        validate_doc(doc)
        payload = json.dumps(doc)
        now = time.time()
        with self._session() as conn:
            conn.execute(
                "INSERT INTO profiles (name, is_active, doc, updated_ts) "
                "VALUES (?, COALESCE((SELECT is_active FROM profiles WHERE name = ?), 0), "
                "?, ?) "
                "ON CONFLICT(name) DO UPDATE SET doc = excluded.doc, "
                "updated_ts = excluded.updated_ts",
                (name, name, payload, now),
            )

    def delete(self, name: str) -> None:
        with self._session() as conn:
            conn.execute("DELETE FROM profiles WHERE name = ?", (name,))

    def set_active(self, name: str) -> None:
        with self._session() as conn:
            exists = conn.execute(
                "SELECT 1 FROM profiles WHERE name = ?", (name,)
            ).fetchone()
            if exists is None:
                raise ValueError("no such profile: %s" % name)
            conn.execute("UPDATE profiles SET is_active = 0 WHERE is_active = 1")
            conn.execute("UPDATE profiles SET is_active = 1 WHERE name = ?", (name,))

    def seed_default_if_empty(self, default_doc: dict, name: str = "default") -> bool:
        """If no profiles exist, insert `default_doc` as `name` and make it active.
        Returns True if it seeded, False if profiles already existed."""
        with self._session() as conn:
            row = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()
            if row[0] > 0:
                return False
        self.put(name, default_doc)
        self.set_active(name)
        return True
