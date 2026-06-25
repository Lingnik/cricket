"""Pre-parse a cached SW1 wiki RPlog page into per-turn JSONL rows.

This is the DETERMINISTIC half of the log->dataset protocol. It does the
mechanical work that must be identical across every log:

  * split the cache header (KEY: value lines) and the {{rplog}} infobox into
    `meta` rows (title, date, setting, author, characters, synopsis, ...);
  * segment the body into blocks (one block == one blank-line-separated pose);
  * clean wikitext (``[[link|disp]]`` -> disp, HTML entities, ''/''' emphasis);
  * encode each block to a single MUSH-style line: a leading indent run becomes
    the literal ``%t`` and internal line breaks become the literal ``%r``.

It does NOT decide who posed each block or whether Cricket is in the scene --
that is the interpretive half, left to an attribution pass (a human/LLM reading
the raw log + this output). Body rows are emitted with ``type:"pose"`` and
``actor:null`` as placeholders for that pass to fill in.

Usage:
    python tools/rplog_to_jsonl.py <page.txt> [--out out.jsonl]
    python tools/rplog_to_jsonl.py <page.txt>            # JSONL to stdout
"""

import argparse
import html
import json
import re
import sys

# --- wikitext cleanup ---------------------------------------------------------

_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_BOLD_RE = re.compile(r"'''(.+?)'''")
_ITALIC_RE = re.compile(r"''(.+?)''")
_EXTLINK_RE = re.compile(r"\[(?:https?|ftp)://\S+?(?:\s+([^\]]+))?\]")
_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_WS_RUN_RE = re.compile(r"[ \t]{2,}")
# leading indent: any run of &nbsp; / spaces / tabs at the very start of a line
_INDENT_RE = re.compile(r"^(?:&nbsp;| |[ \t])+")


def _deref_link(m):
    """[[target|display]] -> display ; [[ns:target]] -> target (no namespace)."""
    inner = m.group(1)
    disp = inner.split("|", 1)[1] if "|" in inner else inner
    disp = disp.strip()
    # strip a leading namespace like ":starwars:" or "Category:" on bare links
    if "|" not in inner:
        disp = disp.lstrip(":")
        if ":" in disp and "/" not in disp.split(":", 1)[0]:
            disp = disp.split(":", 1)[1]
    disp = disp.split("#", 1)[0]  # drop section anchors
    return disp.strip()


def clean_inline(text):
    """Strip wiki markup from a fragment that is already a single logical line."""
    text = _LINK_RE.sub(_deref_link, text)
    text = _EXTLINK_RE.sub(lambda m: (m.group(1) or "").strip(), text)
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = html.unescape(text)            # &amp; &lt; &quot; &#39; ...
    text = text.replace(" ", " ")    # any surviving nbsp -> space
    text = _WS_RUN_RE.sub(" ", text)
    return text.strip()


def encode_block(raw_lines):
    """Encode the physical lines of one block into a single %t/%r MUSH line.

    A leading indent run on a physical line -> a single leading ``%t``.
    Physical line breaks within the block -> ``%r``.
    """
    encoded = []
    for line in raw_lines:
        indented = bool(_INDENT_RE.match(line))
        line = _INDENT_RE.sub("", line)            # drop the literal indent run
        line = _BR_RE.sub("\x00", line)            # protect interior <br>
        line = clean_inline(line)
        for i, seg in enumerate(line.split("\x00")):
            seg = seg.strip()
            prefix = "%t" if (i == 0 and indented) else ""
            if seg or prefix:
                encoded.append(prefix + seg)
    return "%r".join(encoded)


# --- page structure -----------------------------------------------------------

_DIVIDER_RE = re.compile(r"^=+\s*$")
_BLANK_RE = re.compile(r"^(?:&nbsp;|<\s*br\s*/?\s*>|\s)*$", re.IGNORECASE)


def is_blank(line):
    """True if the line is structurally empty -- whitespace and/or only the
    cosmetic markers (&nbsp;, <br>) that render as a blank line on the wiki."""
    return bool(_BLANK_RE.match(line))


def body_line_span(text):
    """Return (body_start_idx, last_idx, lines) -- 0-based inclusive range of
    the body (after the ===== header divider and the {{rplog}} template)."""
    lines = text.splitlines()
    n = len(lines)
    d = None
    for i, l in enumerate(lines):
        if _DIVIDER_RE.match(l) and len(l.strip()) >= 10:
            d = i
            break
    j = 0 if d is None else d + 1
    while j < n and lines[j].strip() == "":
        j += 1
    if j < n and lines[j].lstrip().startswith("{{"):
        depth = 0
        while j < n:
            depth += lines[j].count("{{") - lines[j].count("}}")
            j += 1
            if depth <= 0:
                break
    while j < n and (lines[j].strip() == "" or re.match(r"^-{3,}$", lines[j].strip())):
        j += 1
    return j, n - 1, lines


def render_numbered(text):
    """Render ONLY the non-blank body lines, each prefixed with its raw line
    number. The labeler echoes the prepended number -- there is nothing to count
    or skip, which removes the line-numbering ambiguity entirely."""
    start, last, lines = body_line_span(text)
    out, nums = [], []
    for i in range(start, last + 1):
        if is_blank(lines[i]):
            continue
        out.append("%d| %s" % (i + 1, lines[i]))
        nums.append(i + 1)
    return "\n".join(out), (nums[0] if nums else 0), (nums[-1] if nums else 0)


def split_header(text):
    """Return (header_dict, rest) splitting on the first ===... divider line."""
    header, lines = {}, text.splitlines()
    for i, line in enumerate(lines):
        if _DIVIDER_RE.match(line) and len(line.strip()) >= 10:
            return header, "\n".join(lines[i + 1:])
        m = re.match(r"^([A-Z][A-Z0-9 _()]+?):\s*(.*)$", line)
        if m:
            header[m.group(1).strip()] = m.group(2).strip()
    return header, text  # no divider -> treat all as body


def extract_template(text):
    """Pull the leading {{...rplog...}} infobox. Return (params, body_rest).

    Brace-matched so a closing }} inside the body is not mistaken for the end.
    """
    s = text.lstrip()
    if not s.lower().startswith("{{"):
        return {}, text
    depth, end = 0, None
    for i in range(len(s)):
        if s.startswith("{{", i):
            depth += 1
        elif s.startswith("}}", i):
            depth -= 1
            if depth == 0:
                end = i + 2
                break
    if end is None:
        return {}, text
    inner = s[2:end - 2]
    body = s[end:]
    # split params on '|' that are NOT the pipe inside a [[target|display]] link
    inner = re.sub(r"\[\[[^\]]*\]\]",
                   lambda m: m.group(0).replace("|", "\x01"), inner)
    parts = inner.split("|")
    params = {}
    for part in parts:
        part = part.replace("\x01", "|")
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip().lower()
            if k:
                params[k] = v.strip()
    # the leading token before the first '|' is the template name; ignore it
    return params, body


def parse_characters(field):
    """characters=`[[A]]<br>[[B|b]] (NPC)` -> ['A', 'b (NPC)']."""
    out = []
    for chunk in _BR_RE.split(field):
        name = clean_inline(chunk).strip()
        if name:
            out.append(name)
    return out


# --- main assembly ------------------------------------------------------------

def parse_page(text):
    rows = []
    header, after_header = split_header(text)
    params, body = extract_template(after_header)

    def meta(key, value):
        if value not in (None, "", []):
            rows.append({"type": "meta", "key": key, "actor": None,
                         "text": value if isinstance(value, str) else json.dumps(value)})

    title = params.get("title") or header.get("TITLE", "").split(":", 1)[-1]
    meta("title", title.strip())
    meta("date", params.get("date") and clean_inline(params["date"]) or header.get("RL_DATE", ""))
    meta("aby", header.get("ABY", ""))
    meta("author", clean_inline(params.get("author", "")))
    meta("setting", clean_inline(params.get("setting", "")))
    chars = parse_characters(params.get("characters", "")) or \
        [c.strip() for c in header.get("CHARACTERS", "").split(",") if c.strip()]
    if chars:
        rows.append({"type": "meta", "key": "characters", "actor": None,
                     "text": ", ".join(chars), "roster": chars})
    meta("factions", header.get("FACTIONS", ""))
    meta("synopsis", clean_inline(params.get("synopsis", "")))

    # body: strip a leading horizontal rule, then segment on blank lines
    body = re.sub(r"^\s*-{3,}\s*$", "", body, flags=re.MULTILINE)
    blocks, cur = [], []
    for line in body.splitlines():
        if line.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append(cur)

    for blk in blocks:
        encoded = encode_block(blk)
        if encoded:
            rows.append({"type": "pose", "key": None, "actor": None, "text": encoded})

    for i, r in enumerate(rows):
        r_with_seq = {"seq": i}
        r_with_seq.update(r)
        rows[i] = r_with_seq
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page")
    ap.add_argument("--out")
    ap.add_argument("--render", action="store_true",
                    help="emit line-numbered body for the labeler instead of JSONL")
    args = ap.parse_args()
    with open(args.page, encoding="utf-8") as fh:
        text = fh.read()
    if args.render:
        body, a, b = render_numbered(text)
        sys.stderr.write("body lines %d..%d\n" % (a, b))
        (open(args.out, "w", encoding="utf-8") if args.out else sys.stdout).write(body + "\n")
        return
    rows = parse_page(text)
    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    for r in rows:
        out.write(json.dumps(r, ensure_ascii=False) + "\n")
    if args.out:
        out.close()
        sys.stderr.write("wrote %d rows -> %s\n" % (len(rows), args.out))


if __name__ == "__main__":
    main()
