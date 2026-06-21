#!/usr/bin/env python3
"""Search the wiki cache and return resolvable handles (title + date).

Filters wiki-cache/index.jsonl by structured fields and/or matches a term against
titles+summaries (default) or full page text (--grep). Output lines are titles you
can feed straight to lookup.py.

Usage:
    python3 tools/search.py "cloud city"                     # term in title/summary
    python3 tools/search.py --character "Jessalyn Valios"    # logs featuring her
    python3 tools/search.py --character "Lorn Rhys" --aby 33
    python3 tools/search.py "taser" --grep                   # term in full page text
    python3 tools/search.py --character X --ns 100 --limit 50
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(os.path.dirname(HERE), "knowledge", "runtime", "wiki")


def year_of(rl_date):
    m = re.search(r"(19|20)\d\d", rl_date or "")
    return int(m.group(0)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("term", nargs="?", default="")
    ap.add_argument("--character")
    ap.add_argument("--faction")
    ap.add_argument("--aby", type=int)
    ap.add_argument("--year", type=int, help="real-world year from rl_date")
    ap.add_argument("--ns", type=int, help="namespace (100=RPlog, 0=Main article)")
    ap.add_argument("--grep", action="store_true", help="match term in full page text")
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    term = args.term.lower()
    rows = []
    with open(os.path.join(CACHE, "index.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            if args.ns is not None and r["ns"] != args.ns:
                continue
            if args.character and args.character not in r.get("characters", []):
                continue
            if args.faction and args.faction not in r.get("factions", []):
                continue
            if args.aby is not None and r.get("aby_year") != args.aby:
                continue
            if args.year is not None and year_of(r.get("rl_date")) != args.year:
                continue
            if term:
                if args.grep:
                    txt = open(os.path.join(CACHE, r["path"]), errors="ignore").read().lower()
                    if term not in txt:
                        continue
                else:
                    hay = (r["title"] + " " + r.get("summary", "")).lower()
                    if term not in hay:
                        continue
            rows.append(r)

    rows.sort(key=lambda r: (r.get("rl_date") or "", r["title"]))
    for r in rows[: args.limit]:
        date = r.get("rl_date") or "?"
        aby = r.get("aby_year")
        aby = f"{aby} ABY" if aby is not None else "?"
        print(f"{r['ns_name']:7} | {date:10} | {aby:7} | {r['title']}")
    if len(rows) > args.limit:
        print(f"... {len(rows)-args.limit} more (raise --limit)", file=sys.stderr)
    print(f"[{len(rows)} match(es)]", file=sys.stderr)


if __name__ == "__main__":
    main()
