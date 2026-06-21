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

# Subject forms that mark CRICKET as the ACTING subject of a pose (his own action or
# speech) -- as opposed to a paragraph where another character merely references him.
_SUBJECT = (
    r"(?:Cricket|The little astromech|The astromech|The droid|"
    r"The R2(?: unit)?|R2-CT|KRKT)"
)
_OPEN = '"'
_CLOSE = '"'
_NOTCLOSE = r'[^"]'

# He leads the paragraph outright (optionally behind a pose-action asterisk)...
_LEAD_SUBJECT = re.compile(r"^\*?\s*" + _SUBJECT + r"\b", re.IGNORECASE)
# ...or it opens with dialogue and he is the SPEAKER: his subject right after the closing
# quote, or a "...from <subject>" speech-source attribution. Addressee mentions
# ("...to Cricket") are intentionally not matched.
_SPEAKER_AFTER_QUOTE = re.compile(
    r"^" + _OPEN + _NOTCLOSE + r"*" + _CLOSE + r"[\s,]*" + _SUBJECT + r"\b",
    re.IGNORECASE,
)
_FROM_SUBJECT = re.compile(
    r"^" + _OPEN + _NOTCLOSE + r"*" + _CLOSE
    + r"[^.]*?\bfrom\b\s+(?:\w+\s+){0,3}?" + _SUBJECT + r"\b",
    re.IGNORECASE,
)
_MIN_LEN = 40


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
    """True only when CRICKET is the acting subject of this pose -- he leads the paragraph
    or is the speaker of its opening dialogue. Paragraphs that merely reference him (some
    other character's pose) are rejected."""
    p = para.strip()
    if len(p) < _MIN_LEN:
        return False
    return bool(
        _LEAD_SUBJECT.match(p)
        or _SPEAKER_AFTER_QUOTE.match(p)
        or _FROM_SUBJECT.match(p)
    )


# The raw logs live here once the corpus is materialized into the tree.
DEFAULT_CORPUS_DIR = "knowledge/sources/cricket-logs/wiki"

_YEAR_RE = re.compile(r"^(\d{4})")


def _log_year(name: str):
    """Parse the leading 4-digit year from a log filename (e.g. '2024 - Title.txt',
    '2006-02 - Title.txt'), or None if it has none."""
    m = _YEAR_RE.match(name)
    return int(m.group(1)) if m else None


def make_replay_cases(
    corpus_dir: str = DEFAULT_CORPUS_DIR,
    context_window: int = 3,
    per_log: int = 1,
    min_year=None,
) -> list:
    """Walk *.txt logs under corpus_dir and emit replay case dicts. Missing dir -> [].

    `min_year`: when set, only logs whose filename leads with a year >= min_year are
    used. Cricket evolved over 24 years (a competent astromech in the 2000s, an unhinged
    crime-droid by the 2020s), so judging the present-day persona is only fair against
    recent references. None (default) uses every log.
    """
    if not corpus_dir or not os.path.isdir(corpus_dir):
        return []
    cases = []
    for name in sorted(os.listdir(corpus_dir)):
        if not name.endswith(".txt"):
            continue
        if min_year is not None:
            year = _log_year(name)
            if year is None or year < min_year:
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
