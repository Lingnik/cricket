"""Build data/dataset/index.jsonl + a human-readable manifest from the per-log
JSONL files. Validates each file (contiguous seqs, faithful row count vs the
pre-parse) and tallies Cricket's turns. Run after the attribution fan-out.

    python tools/dataset_index.py
"""

import collections
import glob
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "dataset")


def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def main():
    # authoritative per-log verdicts from the attribution pass (QUALIFY /
    # PRESENT_MINOR / REFERENCE); PRESENT_MINOR vs REFERENCE cannot be derived
    # from turn counts, so we trust the reader's judgement here.
    vpath = os.path.join(ROOT, "_verdicts.json")
    verdicts = {}
    if os.path.exists(vpath):
        for r in json.load(open(vpath, encoding="utf-8")):
            verdicts[r["name"]] = r["verdict"]

    index = []
    for path in sorted(glob.glob(os.path.join(ROOT, "RPlog_*.jsonl"))):
        name = os.path.basename(path)[:-6]
        rows = load(path)
        pre = os.path.join(ROOT, "_preparse", name + ".jsonl")
        pre_n = len(load(pre)) if os.path.exists(pre) else None
        actors = collections.Counter(
            r.get("actor") for r in rows if r.get("type") == "pose")
        cricket = actors.get("Cricket", 0)
        seqs = [r.get("seq") for r in rows]
        contiguous = seqs == list(range(len(rows)))
        # >= pre_n because an agent may split a bundled block into two rows
        faithful = pre_n is None or len(rows) >= pre_n
        verdict = verdicts.get(name) or ("QUALIFY" if cricket else "PRESENT_MINOR")
        index.append({
            "name": name,
            "verdict": verdict,
            "rows": len(rows),
            "preparse_rows": pre_n,
            "poses": sum(actors.values()),
            "cricket_turns": cricket,
            "distinct_actors": len([a for a in actors if a]),
            "contiguous_seqs": contiguous,
            "faithful": faithful,
            "top_actors": actors.most_common(5),
        })

    with open(os.path.join(ROOT, "index.jsonl"), "w", encoding="utf-8") as fh:
        for r in index:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    q = [r for r in index if r["verdict"] == "QUALIFY"]
    pm = [r for r in index if r["verdict"] == "PRESENT_MINOR"]
    ref = [r for r in index if r["verdict"] == "REFERENCE"]
    lines = ["# Cricket RP-log turn dataset -- manifest", ""]
    lines.append(f"- Built logs: {len(index)}")
    lines.append(f"- QUALIFY (Cricket has own poses): {len(q)}")
    lines.append(f"- PRESENT_MINOR (present, no own Cricket pose): {len(pm)}")
    if ref:
        lines.append(f"- REFERENCE still present (should be relocated): "
                     f"{[r['name'] for r in ref]}")
    lines.append(f"- Total rows: {sum(r['rows'] for r in index)}")
    lines.append(f"- Total poses: {sum(r['poses'] for r in index)}")
    native = sum(r['cricket_turns'] for r in index)
    embedded_path = os.path.join(ROOT, "cricket_embedded.jsonl")
    embedded = len(load(embedded_path)) if os.path.exists(embedded_path) else 0
    lines.append(f"- Cricket turns (native poses): {native}")
    if embedded:
        lines.append(f"- Cricket turns (carved from minor logs, "
                     f"cricket_embedded.jsonl): {embedded}")
        lines.append(f"- Cricket turns (combined training pool): {native + embedded}")
    bad = [r['name'] for r in index if not (r['contiguous_seqs'] and r['faithful'])]
    lines.append(f"- Integrity issues: {bad or 'none'}")
    lines.append("")
    lines.append("| Log | Cricket turns | Poses | Rows | Top actors |")
    lines.append("|---|---:|---:|---:|---|")
    for r in sorted(index, key=lambda r: -r["cricket_turns"]):
        top = ", ".join(f"{a}:{n}" for a, n in r["top_actors"] if a)
        lines.append(f"| {r['name'][6:]} | {r['cricket_turns']} | "
                     f"{r['poses']} | {r['rows']} | {top} |")
    with open(os.path.join(ROOT, "MANIFEST.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
