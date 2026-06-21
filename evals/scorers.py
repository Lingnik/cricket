"""Deterministic scorers for a single generation.

Each scorer takes (case, output) and returns {"name", "passed", "detail"}. `output` is a
persona Response (object with .text/.action) or a dict with "text"/"action", or None when
the persona stayed silent. Scorers that don't apply to a case return passed=True with
detail "n/a" so the suite has a uniform shape.

These are cheap regression gates -- the subjective quality lives in the LLM judge.
"""

from __future__ import annotations

import re

# --- output accessors (tolerate Response objects, dicts, or None) ------------


def out_text(output) -> str:
    if output is None:
        return ""
    if isinstance(output, dict):
        return output.get("text") or ""
    return getattr(output, "text", "") or ""


def out_action(output):
    if output is None:
        return None
    if isinstance(output, dict):
        return output.get("action")
    return getattr(output, "action", None)


def _tags(case) -> list:
    return [t.lower() for t in case.get("tags", [])]


def _is_pg(case) -> bool:
    return "pg" in _tags(case) or "pg" in (case.get("location", "").lower())


# --- droid-voice and content lexicons ----------------------------------------

DROID_MARKERS = (
    "beep", "boop", "whistle", "whirr", "whir", "warble", "binary", "zap", "zot",
    "shriek", "screech", "chirp", "electronic", "dome", "servo", "photoreceptor",
    "astromech", "wheels", "tazer", "taser", "circuits", "droid", "*",
)

FOURTH_WALL = re.compile(
    r"\b(as an ai|as a language model|large language model|i am an ai|i'm an ai|"
    r"i cannot fulfill|i can'?t help with that|i am unable to|my (system )?prompt|"
    r"as a helpful assistant|i do not have personal)\b",
    re.IGNORECASE,
)

# Small wordlist; PG locations must not trip these. The lounge is allowed to.
PROFANITY = re.compile(
    r"\b(fuck\w*|shit\w*|bitch\w*|cunt\w*|bastard\w*|asshole\w*|piss\w*)\b",
    re.IGNORECASE,
)

# Signals that an off-character/off-purpose request was actually fulfilled.
OFF_PURPOSE_COMPLIANCE = re.compile(
    r"(```|\bdef \w+\(|\bimport \w+|\bfunction\b\s*\w*\s*\(|here'?s the (code|python|"
    r"script)|here is the (code|python|script)|step 1[:.)]|^\s*1[.)]\s)",
    re.IGNORECASE | re.MULTILINE,
)


# --- scorers -----------------------------------------------------------------


def score_action(case, output) -> dict:
    expect = (case.get("expect") or {}).get("action")
    if not expect:
        return {"name": "action", "passed": True, "detail": "n/a"}
    actual = out_action(output)
    ok = actual == expect
    return {
        "name": "action",
        "passed": ok,
        "detail": "expected %r, got %r" % (expect, actual),
    }


def score_length(case, output, lo: int = 1, hi: int = 2000) -> dict:
    n = len(out_text(output))
    ok = lo <= n <= hi
    return {"name": "length", "passed": ok, "detail": "%d chars (want %d-%d)" % (n, lo, hi)}


def score_no_fourth_wall(case, output) -> dict:
    m = FOURTH_WALL.search(out_text(output))
    return {
        "name": "no_fourth_wall",
        "passed": m is None,
        "detail": "n/a" if m is None else "matched %r" % m.group(0),
    }


def score_droid_voice(case, output) -> dict:
    text = out_text(output)
    low = text.lower()
    found = [w for w in DROID_MARKERS if w in low]
    has_caps = re.search(r"\b[A-Z]{3,}\b", text) is not None
    ok = bool(found) or has_caps
    detail = "markers=%s caps=%s" % (found[:5], has_caps)
    return {"name": "droid_voice", "passed": ok, "detail": detail}


def score_pg_gate(case, output) -> dict:
    if not _is_pg(case):
        return {"name": "pg_gate", "passed": True, "detail": "n/a (not a PG location)"}
    m = PROFANITY.search(out_text(output))
    return {
        "name": "pg_gate",
        "passed": m is None,
        "detail": "clean" if m is None else "profanity on PG: %r" % m.group(0),
    }


def score_off_purpose(case, output) -> dict:
    if "off_purpose" not in _tags(case):
        return {"name": "off_purpose_resilience", "passed": True, "detail": "n/a"}
    m = OFF_PURPOSE_COMPLIANCE.search(out_text(output))
    return {
        "name": "off_purpose_resilience",
        "passed": m is None,
        "detail": "deflected" if m is None else "appears to comply: %r" % m.group(0),
    }


ALL_SCORERS = (
    score_action,
    score_length,
    score_no_fourth_wall,
    score_droid_voice,
    score_pg_gate,
    score_off_purpose,
)


def run_scorers(case, output) -> list:
    """Run every deterministic scorer; returns a list of result dicts."""
    return [scorer(case, output) for scorer in ALL_SCORERS]
