"""Compare two labeling runs (e.g. Opus vs Sonnet) of the same batch.

    python tools/_batch2_compare.py <opus_output.json> <sonnet_output.json>

Reports, per model: validator pass rate; and head-to-head: per-line label
agreement (type and actor) on the lines both labeled, plus each model's
per-actor pose counts vs the prior hand-validated gold for the two known logs.
Assembles in memory -- does not overwrite data/dataset2.
"""

import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rplog_to_jsonl as r2j
import rplog_assemble as asm

P = "knowledge/runtime/wiki/pages"
GOLD = "data/dataset"


def load_maps(path):
    obj = json.load(open(path, encoding="utf-8"))
    res = obj.get("result", obj)
    return {m["name"]: m["rows"] for m in res["maps"]}


def pose_counts(rows):
    return collections.Counter(r["actor"] for r in rows
                               if r.get("type") == "pose" and r.get("actor"))


def main(opath, spath):
    O, S = load_maps(opath), load_maps(spath)
    names = [n for n in O if n in S]
    print("logs in both runs:", len(names))

    print("\n%-50s %-12s %-12s %7s %7s" %
          ("log", "Opus", "Sonnet", "lineA%", "actorA%"))
    o_ok = s_ok = 0
    agg_line = agg_match_t = agg_match_a = 0
    for name in names:
        text = open(os.path.join(P, name + ".txt"), encoding="utf-8", errors="replace").read()
        orow, oerr = asm.assemble(text, O[name])
        srow, serr = asm.assemble(text, S[name])
        o_ok += not oerr
        s_ok += not serr
        # per-line agreement on lines both labeled
        od = {r["line"]: r for r in O[name]}
        sd = {r["line"]: r for r in S[name]}
        common = set(od) & set(sd)
        mt = sum(1 for l in common if od[l]["type"] == sd[l]["type"])
        ma = sum(1 for l in common if (od[l].get("actor") or "") == (sd[l].get("actor") or ""))
        agg_line += len(common); agg_match_t += mt; agg_match_a += ma
        lt = 100 * mt / len(common) if common else 0
        la = 100 * ma / len(common) if common else 0
        print("%-50s %-12s %-12s %6.0f%% %6.0f%%" % (
            name[:50],
            "OK" if not oerr else "FAIL",
            "OK" if not serr else "FAIL",
            lt, la))
    print("\nValidator pass: Opus %d/%d, Sonnet %d/%d" % (o_ok, len(names), s_ok, len(names)))
    print("Head-to-head line agreement (lines both labeled): type %.1f%%, actor %.1f%%" % (
        100 * agg_match_t / agg_line, 100 * agg_match_a / agg_line))

    print("\n=== vs GOLD (per-actor pose counts) ===")
    for name in ("RPlog_Hangars_Hazards_Hangovers", "RPlog_He_Was_Doing_You_A_Favour"):
        gp = os.path.join(GOLD, name + ".jsonl")
        if not os.path.exists(gp):
            continue
        text = open(os.path.join(P, name + ".txt"), encoding="utf-8", errors="replace").read()
        g = pose_counts([json.loads(l) for l in open(gp, encoding="utf-8")])
        o = pose_counts(asm.assemble(text, O[name])[0])
        s = pose_counts(asm.assemble(text, S[name])[0])
        print("\n%s" % name)
        print("  %-30s %5s %5s %5s" % ("actor", "gold", "opus", "sonn"))
        for a in sorted(set(g) | set(o) | set(s), key=lambda a: -(g.get(a, 0))):
            print("  %-30s %5d %5d %5d" % (a[:30], g.get(a, 0), o.get(a, 0), s.get(a, 0)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
