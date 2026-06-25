"""Build the FULL-corpus fine-tune set from data/dataset_full/_assembled.

Unlike build_finetune.main() (which targets the 29 dataset2 logs), this walks all
1,220 assembled logs (~74k attributed poses across ~1,573 actors). Raw, that set is
both impractically large and badly imbalanced (a few prolific characters dominate),
which would teach the model those voices instead of the conditioned "pose anyone from
their profile/scene" skill. So we apply a balancing curriculum:

  * ALL Cricket poses, upweighted to ~CAP_PROFILED (the headline character is rare --
    only ~52 poses -- so we repeat them so he isn't drowned out);
  * profiled characters (those with a sheet): capped at CAP_PROFILED each;
  * everyone else: capped at CAP_TAIL each (breadth without domination).

Meta is synthesized per log: title from the _labeled curation, present-cast derived
from the pose actors (assembled meta has no 'characters' key). Reuses build_finetune's
build_sample so the rendered shape is byte-identical to the dataset2 path.

    python tools/build_finetune_full.py [CAP_PROFILED] [CAP_TAIL]
"""

import collections
import glob
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_finetune as bf

bf.INPUT_BUDGET = 2100                      # match MAXLEN 2560 training window
ASM = "data/dataset_full/_assembled"
LAB = "data/dataset_full/_labeled"
OUT = "data/finetune/train_full.jsonl"


def main():
    cap_p = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    cap_t = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    random.seed(0)

    cache = {}                              # log -> (meta, body)
    by_actor = collections.defaultdict(list)
    for af in sorted(glob.glob(os.path.join(ASM, "*.jsonl"))):
        name = os.path.basename(af)[:-6]
        rows = [json.loads(l) for l in open(af, encoding="utf-8")]
        meta = {r["key"]: r["text"] for r in rows if r["type"] == "meta"}
        body = [r for r in rows if r["type"] != "meta"]
        lab_path = os.path.join(LAB, name + ".json")
        if os.path.exists(lab_path):
            meta["title"] = json.load(open(lab_path, encoding="utf-8")).get("title", meta.get("title", ""))
        present = sorted({r["actor"] for r in body if r.get("type") == "pose" and r.get("actor")})
        meta["characters"] = ", ".join(present)
        cache[name] = (meta, body)
        for i, r in enumerate(body):
            if r.get("type") == "pose" and r.get("actor"):
                by_actor[r["actor"]].append((name, i))

    selected = []
    for actor, items in by_actor.items():
        if actor == "Cricket":
            sel = list(items)
            while len(sel) < cap_p:         # upweight the rare headline character
                sel += items
            sel = sel[:cap_p]
        else:
            cap = cap_p if bf.profile_for(actor) else cap_t
            sel = items if len(items) <= cap else random.sample(items, cap)
        selected.extend(sel)
    random.shuffle(selected)

    n = prof = 0
    with open(OUT, "w", encoding="utf-8") as fh:
        for name, idx in selected:
            meta, body = cache[name]
            r = body[idx]
            sample, _, _ = bf.build_sample(meta, body[:idx], r["actor"], r["text"])
            fh.write(json.dumps(sample, ensure_ascii=False) + "\n")
            n += 1
            if "(No profile on file" not in sample["messages"][0]["content"]:
                prof += 1
    print("curriculum: profiled cap %d / tail cap %d" % (cap_p, cap_t))
    print("wrote %d samples (%d profiled, %d no-profile) -> %s" % (n, prof, n - prof, OUT))
    steps = n / 8
    print("~%d steps/epoch at effective batch 8 (~%.0fh/epoch at 43s/step)" % (steps, steps * 43 / 3600))


if __name__ == "__main__":
    main()
