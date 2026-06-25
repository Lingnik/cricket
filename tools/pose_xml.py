"""XML pose-tagging shared by prompt rendering and serve-side parsing.

The scene transcript AND the model's output use the same lightweight tags, so:
  * multi-line %r/%t poses delimit cleanly (flat "Name: text" is ambiguous), and
  * a generation that puppets a second character is a PARSE-detectable violation,
    not a heuristic guess -- replacing the regex/role-break cleanup.

Tags (inner text keeps MUSH markup, %r=newline %t=indent; no escaping needed --
the text has no real newlines or angle brackets):
    <pose char="Name">...</pose>     one character's turn
    <narration>...</narration>       room/scene/object description, no actor
    <ooc>...</ooc>                    out-of-character

Output contract the model is trained to follow: emit EXACTLY ONE
<pose char="TARGET">...</pose> and nothing else.
"""

import re

_HTML = re.compile(r"</?(?:blockquote|p|br|div|span|i|b|em|strong)\s*/?>", re.I)
_POSE_OPEN = re.compile(r'<pose\s+char="([^"]*)"\s*>')


def clean(text):
    """Strip residual wiki/HTML markup that leaked into a row's text."""
    return _HTML.sub("", text or "").strip()


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


# --- render (prompt side) ----------------------------------------------------

def render_row(r):
    t, txt = r.get("type"), clean(r.get("text"))
    if not txt:
        return ""
    actor = (r.get("actor") or "").strip()
    if t == "pose" and actor:
        return '<pose char="%s">%s</pose>' % (actor, txt)
    if t == "ooc":
        return "<ooc>%s</ooc>" % txt
    # room / scene / desc / system, and actor-less "poses" (incidental NPC action)
    return "<narration>%s</narration>" % txt


def render_scene(rows):
    """Render a list of body rows (oldest first) into a tagged transcript."""
    return "\n".join(s for s in (render_row(r) for r in rows) if s)


def render_target(actor, text):
    """The assistant training target: the character's pose, tagged."""
    return '<pose char="%s">%s</pose>' % (actor, clean(text))


# --- parse (serve side) ------------------------------------------------------

def parse_generation(raw, expected_char):
    """Turn a raw generation into (pose_text, verdict).

    verdict:
      "ok"        -- one pose for the expected char; inner text returned (%r/%t kept).
      "puppet"    -- a <pose> tag for ANOTHER character appeared; we cut at the first
                     foreign tag (keep only the expected char's pose) and flag it so the
                     caller can log/penalize the puppeting.
      "recovered" -- model emitted bare prose or a truncated/unclosed tag; salvaged.
      "empty"     -- nothing usable.
    """
    raw = (raw or "").strip()

    # 1. cut at the first <pose> tag belonging to anyone but the expected char.
    puppeted = False
    for m in _POSE_OPEN.finditer(raw):
        if _norm(m.group(1)) != _norm(expected_char):
            raw = raw[:m.start()]
            puppeted = True
            break

    # 2. extract the expected char's pose body (closed tag, else to end-of-string
    #    to tolerate truncation at the token cap).
    m = re.search(r'<pose\s+char="[^"]*"\s*>(.*?)(?:</pose>|\Z)', raw, re.S)
    inner = m.group(1) if m else raw
    inner = re.sub(r"</?pose[^>]*>", "", inner)          # drop any stray tag fragments
    inner = clean(inner)

    if not inner:
        return "", "empty"
    if puppeted:
        return inner, "puppet"
    return inner, ("ok" if m else "recovered")


SYSTEM_RULE = (
    "You write a single roleplay pose for the character below, on a text MUSH. Stay strictly in "
    "that character's voice and body. Pose only your own action, speech, and intent -- never "
    "another character's words, actions, or outcomes. Output EXACTLY ONE tag: "
    '<pose char="{name}">...your pose...</pose>, with MUSH markup inside (%r = newline, '
    "%t = indent). Do NOT write a <pose> tag for anyone else, and write nothing outside the tag."
)
