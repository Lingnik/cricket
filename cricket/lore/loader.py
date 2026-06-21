"""Load distilled Cricket lore and assemble retrieval context.

Lore artifacts (produced by the distillation pass) live under a lore directory:
    CRICKET.md              -- character sheet (the system-prompt prefix)
    voice-exemplars.md      -- few-shot voice anchors
    dossiers/<kebab>.md     -- one per recurring character
    index.json              -- {"characters": {Name: [episode, ...]},
                                "episodes": {title: {date, aby, location, cast}}}

The loader is tolerant of missing files, so the bot runs before (or without) a full
corpus. Retrieval is structured by character -- no embeddings: given the cast present in
a scene, assemble the relevant dossiers into a stable, deterministically ordered
"memories block" to inject above the live scene (per the prefix-cache discipline, the
block depends only on the cast, not on call order).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Union

# Two-facet dossier convention. A per-player dossier MAY split its body into facets with
# markdown headers `## IC` and `## OOC` (optionally with trailing text, e.g. "## OOC -- meta"):
#   <shared preamble>
#   ## IC
#   <what Cricket plausibly knows in-universe -- used for room RP>
#   ## OOC
#   <wider meta / teasing / roast ammo -- used on channels>
# `retrieve(scope=...)` returns the shared preamble plus the requested facet. Dossiers with
# NO such headers are single-block and are returned whole under any scope (backward-compatible).
# The richer per-player sheets distilled from the corpus PR should emit this format.
_FACET_HEADER = re.compile(r"(?im)^##[ \t]+(IC|OOC)\b.*$")


def _facet(text: str, scope: Union[str, None]) -> str:
    """Return the part of a dossier relevant to `scope` ("ic"|"ooc"|None).

    None -> whole text. With a scope: if the dossier has no `## IC`/`## OOC` headers,
    return the whole text (legacy single-block). Otherwise return the shared preamble
    (text before the first facet header) plus the requested facet's body; if the requested
    facet is absent, return just the preamble (never leak the other facet).
    """
    if not scope:
        return text
    matches = list(_FACET_HEADER.finditer(text))
    if not matches:
        return text
    want = scope.strip().lower()
    preamble = text[: matches[0].start()].strip()
    for i, m in enumerate(matches):
        if m.group(1).lower() == want:
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            return (preamble + "\n\n" + body).strip() if preamble else body
    return preamble


def kebab(name: str) -> str:
    """Character name -> dossier filename stem: lowercase, apostrophes removed, spaces
    and other separators collapsed to single hyphens. "Ikihsa Enb'Zik" -> "ikihsa-enbzik".
    """
    s = name.strip().lower().replace("'", "")
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_", "."):
            out.append("-")
        # any other punctuation is dropped
    result = "".join(out)
    while "--" in result:
        result = result.replace("--", "-")
    return result.strip("-")


class LoreStore:
    """Read-mostly access to the distilled lore, plus structured-by-character retrieval."""

    def __init__(self, lore_dir: Union[str, Path]) -> None:
        self.dir = Path(lore_dir)
        self._index = self._load_index()
        self._dossiers = self._discover_dossiers()  # kebab stem -> Path

    # -- loading ---------------------------------------------------------------
    def _load_index(self) -> dict:
        p = self.dir / "index.json"
        if not p.exists():
            return {}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _discover_dossiers(self) -> dict:
        out: dict = {}
        d = self.dir / "dossiers"
        if d.is_dir():
            for f in sorted(d.glob("*.md")):
                out[f.stem] = f
        return out

    def _read(self, name: str) -> str:
        p = self.dir / name
        if not p.exists():
            return ""
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            return ""

    # -- accessors -------------------------------------------------------------
    def character_sheet(self) -> str:
        return self._read("CRICKET.md")

    def exemplars(self) -> str:
        return self._read("voice-exemplars.md")

    def known_characters(self) -> list:
        return sorted(self._index.get("characters", {}).keys())

    def dossier(self, name: str) -> Union[str, None]:
        f = self._dossiers.get(kebab(name))
        if f is None:
            return None
        try:
            return f.read_text(encoding="utf-8")
        except OSError:
            return None

    def episodes_for(self, name: str) -> list:
        chars = self._index.get("characters", {})
        if name in chars:
            return list(chars[name])
        low = name.lower()
        for k, v in chars.items():
            if k.lower() == low:
                return list(v)
        return []

    # -- retrieval -------------------------------------------------------------
    def retrieve(self, cast, scope: Union[str, None] = None, max_chars: int = 4000) -> str:
        """Assemble the dossiers for the present cast into a stable memories block.

        `scope` selects the IC or OOC facet of each dossier (see `_facet`): "ic" for room
        RP (canon-plausible knowledge), "ooc" for channels (the wider roast/teasing suite),
        None for the whole dossier. Only characters with a dossier are included; duplicates
        are dropped; output is ordered deterministically (by kebab stem) so the same cast
        always yields the same block regardless of input order, truncated to max_chars.
        """
        seen: set = set()
        chosen = []
        for c in cast:
            k = kebab(c)
            if k and k not in seen and k in self._dossiers:
                seen.add(k)
                chosen.append(c)
        chosen.sort(key=kebab)

        parts: list = []
        for n in chosen:
            text = self.dossier(n)
            if not text:
                continue
            text = _facet(text, scope)
            if not text.strip():
                continue
            piece = "## %s\n%s" % (n, text.strip())
            base = "\n\n".join(parts)
            sep = 2 if base else 0
            if len(base) + sep + len(piece) > max_chars:
                room = max_chars - len(base) - sep
                if room > 0:
                    parts.append(piece[:room])
                break
            parts.append(piece)
        return "\n\n".join(parts).strip()

    # -- bridge to runtime memory ---------------------------------------------
    def seed_actors(self, store) -> int:
        """Register every known character in the runtime actors table so the bot
        recognizes them when they appear live. Lore characters have no live dbref, so
        they are keyed under a synthetic "lore:<kebab>" dbref; the dossier pointer is
        stored in the memory KV (upsert_actor cannot write the notes column). The live
        recognition path is name-based dossier lookup at retrieval time. Returns count.
        """
        count = 0
        for name in self.known_characters():
            stem = kebab(name)
            store.upsert_actor("lore:" + stem, name)
            if stem in self._dossiers:
                store.remember("lore", name, "dossier", stem)
            count += 1
        return count
