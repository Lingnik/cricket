"""Generate poses (current vs Lunaris vs Rocinante) WITH scene context, for an Opus judge pass.

The mechanical panel can't separate the RP tunes on voice/coherence (the marker-word regex
undercounts richer prose). This dumps each model's poses next to the beat they react to, so a
judge can score voice (is this Cricket's crass scheming astromech?) and fit/coherence (does it
react to THIS beat, and end cleanly rather than truncated). thinking off; per-model card sampling.

Usage: python evals/judge_gen.py [n_scenes] [n_samples]  -> writes data/judge_poses.json
"""

import asyncio
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evals.scene_replay import (  # noqa: E402
    DEFAULT_REPORT_LOGS, _ROOT, attribute, cut_points, _generated_pose, paragraphs)
from evals.ab_thinking import CapTracer  # noqa: E402
from evals.ab_models import MODELS, build_persona  # noqa: E402
from cricket.lore.loader import LoreStore  # noqa: E402


def main():
    n_scenes = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    nsamples = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    lore = LoreStore(os.path.join(_ROOT, "knowledge", "runtime", "lore"))
    scenes = []
    for stem in DEFAULT_REPORT_LOGS:
        m = sorted(glob.glob(os.path.join(_ROOT, "knowledge", "sources", "cricket-logs", "wiki", stem + "*")))
        if not m:
            continue
        attributed = attribute(paragraphs(open(m[0], encoding="utf-8", errors="replace").read()), lore)
        cuts = cut_points(attributed)
        if not cuts:
            continue
        cut = cuts[0][0]
        scenes.append((stem[:30], attributed, cut))
        if len(scenes) >= n_scenes:
            break
    out = []
    for label, model, sampling in MODELS:
        tracer = CapTracer()
        persona = build_persona(lore, model, sampling, tracer)
        for sid, attributed, cut in scenes:
            ctx = ["%s: %s" % (s, t[:160]) for s, t in attributed[max(0, cut - 2):cut]]
            for k in range(nsamples):
                tracer.reset()
                pose, _g = asyncio.run(_generated_pose(persona, attributed, cut))
                comp = [r for r in tracer.recs if r.get("kind") == "generate" and r.get("pass") in (None, "compose")]
                clean = comp[-1]["clean_output"] if comp else (pose or "")
                out.append({"model": label.strip(), "scene": sid, "context": ctx, "pose": clean})
                print("  %s %s #%d" % (label.strip(), sid, k))
    path = os.path.join(_ROOT, "data", "judge_poses.json")
    json.dump(out, open(path, "w", encoding="utf-8"), indent=1)
    print("wrote %s (%d poses)" % (path, len(out)))


if __name__ == "__main__":
    main()
