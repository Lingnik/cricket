#!/usr/bin/env python3
"""Build the bundled wiki-cache from a sw1mush-wiki-export directory.

Reads the export's all_pages.jsonl (every wiki page: title, ns, timestamp, text)
and log_index_v2.jsonl (per-RPlog metadata) and writes:

    wiki-cache/pages/<slug>.txt   one raw page per file (metadata header + wikitext)
    wiki-cache/index.jsonl        one record per page (the lookup/search index)

The cache is the committed artifact; this script just regenerates it. Idempotent.

Usage:
    python3 tools/build_cache.py --export-dir ~/git/l/sw1mush-wiki-export \
                                 --out wiki-cache
"""
import argparse, json, os, re, hashlib, sys

NS_NAMES = {
    0: "Main", 1: "Talk", 2: "User", 3: "User_talk", 4: "Project", 5: "Project_talk",
    6: "File", 7: "File_talk", 8: "MediaWiki", 10: "Template", 11: "Template_talk",
    12: "Help", 13: "Help_talk", 14: "Category", 15: "Category_talk",
    100: "RPlog", 101: "RPlog_talk", 102: "Story", 103: "Story_talk",
    104: "Report", 105: "Report_talk", 110: "Forum", 111: "Forum_talk",
    500: "Blog", 502: "Blog_talk",
}


def slugify(title, seen):
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")
    s = re.sub(r"_+", "_", s)[:120] or "page"
    if s.lower() in seen:
        s = f"{s}__{hashlib.sha1(title.encode()).hexdigest()[:8]}"
    seen.add(s.lower())
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export-dir", required=True)
    ap.add_argument("--out", default="knowledge/runtime/wiki")
    args = ap.parse_args()

    exp = os.path.expanduser(args.export_dir)
    all_pages = os.path.join(exp, "all_pages.jsonl")
    log_index = os.path.join(exp, "log_index_v2.jsonl")
    if not os.path.exists(all_pages):
        sys.exit(f"missing {all_pages}")

    # log metadata keyed by title
    logmeta = {}
    if os.path.exists(log_index):
        for line in open(log_index):
            r = json.loads(line)
            logmeta[r["title"]] = r

    pages_dir = os.path.join(args.out, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    seen, n = set(), 0
    with open(os.path.join(args.out, "index.jsonl"), "w") as idx:
        for line in open(all_pages):
            p = json.loads(line)
            title = p["title"]
            ns = p.get("ns", 0)
            slug = slugify(title, seen)
            path = f"pages/{slug}.txt"
            lm = logmeta.get(title, {})

            header = (
                f"TITLE: {title}\n"
                f"NAMESPACE: {ns} ({NS_NAMES.get(ns, 'ns'+str(ns))})\n"
                f"LAST_EDIT: {p.get('timestamp','')}\n"
            )
            if lm:
                header += (
                    f"CHARACTERS: {', '.join(lm.get('characters', []))}\n"
                    f"RL_DATE: {lm.get('rl_date','')}  ABY: {lm.get('aby_year','')}\n"
                    f"FACTIONS: {', '.join(lm.get('factions', []))}\n"
                )
            header += "=" * 70 + "\n"
            with open(os.path.join(args.out, path), "w") as f:
                f.write(header + (p.get("text") or ""))

            rec = {
                "title": title,
                "ns": ns,
                "ns_name": NS_NAMES.get(ns, f"ns{ns}"),
                "path": path,
                "last_edit": p.get("timestamp", ""),
                "characters": lm.get("characters", []),
                "rl_date": lm.get("rl_date", ""),
                "aby_year": lm.get("aby_year"),
                "factions": lm.get("factions", []),
                "summary": lm.get("summary", ""),
            }
            idx.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1

    print(f"wrote {n} pages to {pages_dir} and index.jsonl")


if __name__ == "__main__":
    main()
