#!/usr/bin/env python3
"""Resolve a citation handle to a full cached wiki page.

Bios cite logs as (RPlog:Title, date) and articles as (Article: Title); pass that
title here to print the raw page text. Title match is exact-first, then
case-insensitive, then with/without a namespace prefix (RPlog:, Story:, etc).

Usage:
    python3 tools/lookup.py --title "RPlog:Jessa Drops a Bomb"
    python3 tools/lookup.py --title "Jessalyn Valios"      # article in Main ns
    python3 tools/lookup.py --slug Jessalyn_Valios          # by cache filename slug
    python3 tools/lookup.py --title "..." --meta-only       # header only, no wikitext
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(os.path.dirname(HERE), "wiki-cache")
NS_PREFIXES = ["", "RPlog:", "Story:", "Report:", "Category:", "Template:", "User:"]


def load_index():
    idx = {}
    with open(os.path.join(CACHE, "index.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            idx[r["title"]] = r
    return idx


def resolve(idx, title):
    if title in idx:
        return idx[title]
    low = {t.lower(): t for t in idx}
    for pre in NS_PREFIXES:
        cand = (pre + title).lower()
        if cand in low:
            return idx[low[cand]]
        # also try stripping a prefix the user supplied
    if title.lower() in low:
        return idx[low[title.lower()]]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title")
    ap.add_argument("--slug")
    ap.add_argument("--meta-only", action="store_true")
    args = ap.parse_args()

    if args.slug:
        path = os.path.join(CACHE, "pages", f"{args.slug}.txt")
        if not os.path.exists(path):
            sys.exit(f"no such slug: {args.slug}")
        text = open(path).read()
    elif args.title:
        idx = load_index()
        rec = resolve(idx, args.title)
        if not rec:
            sys.exit(f"not found: {args.title!r} (try tools/search.py to find the title)")
        text = open(os.path.join(CACHE, rec["path"])).read()
    else:
        sys.exit("pass --title or --slug")

    if args.meta_only:
        text = text.split("=" * 70)[0]
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


if __name__ == "__main__":
    main()
