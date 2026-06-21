"""Wire the distilled Cricket character sheet + voice exemplars into the active
profile's prompts.system, in the config DB. Re-run after the lore is regenerated.

    python tools/wire_persona.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, ".")
from cricket.profiles.store import ConfigStore  # noqa: E402

CONFIG_DB = "data/cricket-config.sqlite3"


def main() -> None:
    store = ConfigStore(CONFIG_DB)
    active = store.active()
    if active is None:
        name, doc = "default", store.get("default")
    else:
        name, doc = active
    if doc is None:
        raise SystemExit("no profile to update")

    sheet = Path("lore/CRICKET.md").read_text(encoding="utf-8")
    exemplars = Path("lore/voice-exemplars.md").read_text(encoding="utf-8")
    system = sheet + "\n\n# How you sound -- voice examples\n\n" + exemplars

    doc.setdefault("prompts", {})["system"] = system
    store.put(name, doc)
    store.set_active(name)
    print("wired character sheet into profile %r (system prompt = %d chars)"
          % (name, len(system)))


if __name__ == "__main__":
    main()
