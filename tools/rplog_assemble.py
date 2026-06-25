"""Assemble a final per-log JSONL from a per-line attribution map + the source.

The map (produced by the labeling pass) is a list of {line, type, actor, b?}
covering every non-blank body line. This script owns ALL mechanical work so the
output is deterministic and reproducible from the map:

  * meta rows come from the deterministic header/template parse (rplog_to_jsonl);
  * consecutive labeled lines with the same (type, actor) form one turn -- a new
    turn starts on a type change, an actor change, a `b:true` begin-flag, or a
    blank source line in between;
  * each turn's source lines are sliced verbatim and encoded (indent -> %t,
    line breaks -> %r); the model never reproduced the text, so it is verbatim.

Validators (printed, and gating): every non-blank body line is covered exactly
once, the assembled text round-trips against the source body, and seqs are
contiguous.

    python tools/rplog_assemble.py <page.txt> <map.json> [--out out.jsonl]
"""

import argparse
import json
import os
import sys

import rplog_to_jsonl as r2j

DROP = {"blank", "sep"}
BODY_TYPES = {"pose", "scene", "room", "desc", "ooc", "system"}


def assemble(text, mp):
    start, last, lines = r2j.body_line_span(text)
    body_nums = [i + 1 for i in range(start, last + 1) if not r2j.is_blank(lines[i])]
    body_set = set(body_nums)

    by_line = {}
    errors = []
    for row in mp:
        ln = row["line"]
        if ln in by_line:
            errors.append("duplicate label for line %d" % ln)
        by_line[ln] = row
        if ln not in body_set:
            errors.append("labeled line %d is not a non-blank body line" % ln)
    missing = [n for n in body_nums if n not in by_line]
    if missing:
        errors.append("uncovered body lines: %s%s" % (
            missing[:20], " ..." if len(missing) > 20 else ""))

    # group labeled body lines (in source order) into turns
    turns, cur = [], None
    prev_num = None
    for n in body_nums:
        row = by_line.get(n)
        if row is None:
            cur = None  # gap (uncovered) breaks the run; flagged above
            prev_num = n
            continue
        t, a = row["type"], (row.get("actor") or "").strip()
        blank_between = prev_num is not None and any(
            r2j.is_blank(lines[k]) for k in range(prev_num, n - 1))
        newturn = (cur is None or t != cur["type"] or a != cur["actor"]
                   or row.get("b") or blank_between)
        if newturn:
            cur = {"type": t, "actor": a, "nums": [n]}
            turns.append(cur)
        else:
            cur["nums"].append(n)
        prev_num = n

    rows = [r for r in r2j.parse_page(text) if r["type"] == "meta"]
    for tn in turns:
        if tn["type"] in DROP:
            continue
        raw = [lines[k - 1] for k in tn["nums"]]
        encoded = r2j.encode_block(raw)
        if not encoded:
            continue
        rows.append({"type": tn["type"], "actor": tn["actor"] or None,
                     "text": encoded})
    for i, r in enumerate(rows):
        r2 = {"seq": i}
        r2.update(r)
        rows[i] = r2

    # round-trip: build both sides through the SAME encoder so normalization is
    # symmetric, then strip markers + whitespace and compare.
    def norm(s):
        return "".join(s.replace("%t", "").replace("%r", "").split())
    src_concat = norm(r2j.encode_block([lines[n - 1] for n in body_nums]))
    out_concat = norm("".join(r["text"] for r in rows if r["type"] != "meta"))
    if src_concat != out_concat:
        # locate first divergence for a useful message
        k = next((i for i in range(min(len(src_concat), len(out_concat)))
                  if src_concat[i] != out_concat[i]), min(len(src_concat), len(out_concat)))
        errors.append("round-trip mismatch near %r (src %d chars vs out %d)"
                      % (src_concat[max(0, k - 20):k + 20], len(src_concat), len(out_concat)))

    seqs_ok = [r["seq"] for r in rows] == list(range(len(rows)))
    if not seqs_ok:
        errors.append("non-contiguous seqs")
    return rows, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page")
    ap.add_argument("map")
    ap.add_argument("--out")
    args = ap.parse_args()
    text = open(args.page, encoding="utf-8", errors="replace").read()
    mp = json.load(open(args.map, encoding="utf-8"))
    if isinstance(mp, dict):
        mp = mp.get("rows", mp)
    rows, errors = assemble(text, mp)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    sys.stderr.write("rows=%d  validation=%s\n"
                     % (len(rows), "OK" if not errors else "FAIL"))
    for e in errors:
        sys.stderr.write("  - " + e + "\n")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(main())
