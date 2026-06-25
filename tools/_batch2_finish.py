"""Post-process the validation fan-out: write maps, assemble JSONL, validate,
and compare the two gold logs against the prior hand-validated attribution.

    python tools/_batch2_finish.py <workflow_output.json>
"""

import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import rplog_to_jsonl as r2j
import rplog_assemble as asm

P = "knowledge/runtime/wiki/pages"
OUT = "data/dataset2"
GOLD = "data/dataset"


def pose_counts(rows):
    return collections.Counter(r["actor"] for r in rows
                               if r.get("type") == "pose" and r.get("actor"))


def main(wf_path):
    obj = json.load(open(wf_path, encoding="utf-8"))
    res = obj.get("result", obj)
    maps = res["maps"]
    os.makedirs(os.path.join(OUT, "_maps"), exist_ok=True)
    print("returned %d / %d maps\n" % (res.get("returned"), res.get("attempted")))
    print("%-50s %5s %5s %6s  %s" % ("log", "rows", "poses", "actors", "validate"))
    summary = []
    for mp in maps:
        name = mp["name"]
        json.dump(mp["rows"], open(os.path.join(OUT, "_maps", name + ".json"), "w",
                                   encoding="utf-8"), ensure_ascii=False)
        text = open(os.path.join(P, name + ".txt"), encoding="utf-8", errors="replace").read()
        rows, errors = asm.assemble(text, mp["rows"])
        with open(os.path.join(OUT, name + ".jsonl"), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        pc = pose_counts(rows)
        verdict = "OK" if not errors else "FAIL: " + errors[0][:50]
        print("%-50s %5d %5d %6d  %s" % (name[:50], len(rows), sum(pc.values()), len(pc), verdict))
        summary.append((name, len(rows), errors))

    print("\n=== GOLD comparison (per-line Opus vs prior hand-validated) ===")
    for name in ("RPlog_Hangars_Hazards_Hangovers", "RPlog_He_Was_Doing_You_A_Favour"):
        gpath = os.path.join(GOLD, name + ".jsonl")
        npath = os.path.join(OUT, name + ".jsonl")
        if not (os.path.exists(gpath) and os.path.exists(npath)):
            continue
        g = pose_counts([json.loads(l) for l in open(gpath, encoding="utf-8")])
        n = pose_counts([json.loads(l) for l in open(npath, encoding="utf-8")])
        print("\n%s" % name)
        actors = sorted(set(g) | set(n), key=lambda a: -(g.get(a, 0) + n.get(a, 0)))
        print("  %-32s %5s %5s" % ("actor", "gold", "new"))
        for a in actors:
            flag = "" if g.get(a, 0) and n.get(a, 0) else "  <-- only one side"
            print("  %-32s %5d %5d%s" % (a[:32], g.get(a, 0), n.get(a, 0), flag))

    nfail = sum(1 for _, _, e in summary if e)
    print("\nvalidation: %d OK, %d FAIL" % (len(summary) - nfail, nfail))


if __name__ == "__main__":
    main(sys.argv[1])
