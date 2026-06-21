"""Permission levels and the dbref allowlist.

Authorization gates on dbref, not name: names are mutable and spoofable, dbrefs are
stable. A name fallback exists only for convenience before a dbref is known and should
not be relied on for sensitive commands.
"""

from __future__ import annotations

import enum
from typing import Union

from .mush.events import Actor


class Level(enum.IntEnum):
    """Privilege levels, ordered. Higher value = more privilege.

    A command declares the minimum level it requires; a context is allowed when its
    level is at least that. OPERATOR is the local console (and explicit operators).
    """

    PUBLIC = 0
    ADMIN = 1
    WIZARD = 2
    OPERATOR = 3


class Allowlist:
    """Maps actors to a Level. Unknown actors are PUBLIC."""

    def __init__(
        self,
        by_dbref: Union[dict, None] = None,
        by_name: Union[dict, None] = None,
    ) -> None:
        self._by_dbref = dict(by_dbref or {})
        self._by_name = dict(by_name or {})

    def grant(self, dbref: str, level: Level) -> None:
        self._by_dbref[dbref] = level

    def grant_name(self, name: str, level: Level) -> None:
        self._by_name[name] = level

    def level_for(self, actor: Actor) -> Level:
        if actor.dbref is not None and actor.dbref in self._by_dbref:
            return self._by_dbref[actor.dbref]
        if actor.name in self._by_name:
            return self._by_name[actor.name]
        return Level.PUBLIC
