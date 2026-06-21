"""Corpus-replay case generation (best-effort).

Given a raw RP log, strip the wiki markup, split into pose paragraphs, find a Cricket pose,
and emit a replay case: the scene-so-far becomes `context`, and Cricket's actual pose
becomes `reference` (ground truth the judge scores generations against).

The corpus is not in the tree yet, so the directory is a parameter and a missing path
yields an empty list rather than an error. Parsing is heuristic by design.
"""

from __future__ import annotations

import os
import re

_CRICKET = re.compile(r"\bCricket\b|\bR2-CT\b|\bastromech\b", re.IGNORECASE)
_DROID_HINT = re.compile(
    r"\b(beep|boop|whistle|warble|binary|zap|zot|shriek|screech|dome|wheels|taser|"
    r"tazer|droid|astromech)\b",
    re.IGNORECASE,
)


def strip_markup(raw: str) -> str:
    """Remove the wiki/metadata cruft and normalize whitespace to plain paragraphs."""
    text = raw
    # Drop the page-metadata header up to and including the RAW WIKITEXT marker.
    m = re.search(r"==\s*RAW WIKITEXT\s*==", text)
    if m:
        text = text[m.end():]
    # Drop the {{Rplog|...}} infobox (may span lines / be nested-ish).
    text = re.sub(r"\{\{Rplog.*?\}\}", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = text.replace("&nbsp;", " ").replace("<br>", "\n")
    # [[Link|Shown]] -> Shown ; [[Link]] -> Link
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'''?", "", text)  # bold/italic wiki ticks
    return text


def paragraphs(raw: str) -> list:
    text = strip_markup(raw)
    out = []
    for block in re.split(r"\n\s*\n", text):
        cleaned = " ".join(block.split()).strip()
        if cleaned:
            out.append(cleaned)
    return out


def is_cricket_pose(para: str) -> bool:
    return bool(_CRICKET.search(para)) and (
        bool(_DROID_HINT.search(para)) or para.count("Cricket") >= 1
    )


# The raw logs live here once the corpus is materialized into the tree.
DEFAULT_CORPUS_DIR = "corpus/wiki"


def make_replay_cases(
    corpus_dir: str = DEFAULT_CORPUS_DIR, context_window: int = 3, per_log: int = 1
) -> list:
    """Walk *.txt logs under corpus_dir and emit replay case dicts. Missing dir -> []."""
    if not corpus_dir or not os.path.isdir(corpus_dir):
        return []
    cases = []
    for name in sorted(os.listdir(corpus_dir)):
        if not name.endswith(".txt"):
            continue
        with open(os.path.join(corpus_dir, name), "r", encoding="utf-8",
                  errors="replace") as fh:
            paras = paragraphs(fh.read())
        cases.extend(_cases_from_paras(paras, name, context_window, per_log))
    return cases


def _cases_from_paras(paras, name, context_window, per_log) -> list:
    cases = []
    made = 0
    for i, para in enumerate(paras):
        if made >= per_log:
            break
        if i == 0 or not is_cricket_pose(para):
            continue
        context = [
            {"speaker": "scene", "kind": "pose", "text": p}
            for p in paras[max(0, i - context_window):i]
        ]
        if not context:
            continue
        cases.append({
            "id": "replay-%s-%d" % (re.sub(r"[^A-Za-z0-9]+", "-", name)[:40], i),
            "mode": "rp",
            "location": "RP scene",
            "location_kind": "room",
            "directives": "",
            "cast": [],
            "context": context,
            "text": "",
            "expect": {"action": "pose"},
            "reference": para,
            "tags": ["rp", "replay"],
        })
        made += 1
    return cases
