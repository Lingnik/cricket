"""A/B: planning pass ON vs OFF (the #2 experiment), measuring the FULL panel -- not just parrot.

Rebuilds real corpus scenes through the live persona (scene_replay machinery) with inference.thinking
toggled per arm, and scores distributions across several scenes x samples. seed is unset in the
active config, so arms cannot be seed-matched -- this is a distributional comparison (N samples/scene).

Arms:
  A  thinking on  (current: a prescriptive private plan that seeds a verbatim beat)
  B  thinking off (no plan -- retrieval is upstream and unaffected, so this loses no salience)

Pre-registered decision rule (set BEFORE running, so judge/sampler noise can't move the goalposts):
  ADOPT B (drop the planner) if, vs A:
    - voice_rate(B)  >= voice_rate(A) - 0.10   (voice does not drop materially)
    - median_len(B)  >= 0.85 * median_len(A)   (length does not collapse)
  B already wins parrot (structurally 0: no plan to copy) and latency (no think call).
  If B fails either bar, the contingency is arm C (a NON-prescriptive plan) -- not a revived
  prescriptive planner, and not a lorebook (salience is already injected upstream).

Usage: python evals/ab_thinking.py [n_scenes] [n_samples]
"""

import asyncio
import copy
import glob
import os
import re
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evals.scene_replay import (  # noqa: E402
    DEFAULT_REPORT_LOGS, _ROOT, attribute, cut_points, _generated_pose, paragraphs)
from cricket.profiles import ConfigStore  # noqa: E402
from cricket.lore.loader import LoreStore  # noqa: E402
from cricket.lore.vector import VectorIndex  # noqa: E402
from cricket.lore.wiki import WikiIndex  # noqa: E402
from cricket.persona.inference import OllamaInferenceClient  # noqa: E402
from cricket.persona.llm import LlmPersona  # noqa: E402

VOICE = re.compile(r"\b(meatbag|scrap|bolt|fat|idiot|fool|moron|rust|grease|kriff|stupid|"
                   r"zot|slag|junk|worthless|pathetic|spineless|cow|bantha|uppity)\w*", re.I)


class CapTracer:
    def __init__(self):
        self.recs = []

    def emit(self, rec):
        self.recs.append(dict(rec))

    def reset(self):
        self.recs = []


def build_persona(lore, thinking, tracer):
    doc = copy.deepcopy(ConfigStore(os.path.join(_ROOT, "data", "cricket-config.sqlite3")).active()[1])
    doc.setdefault("inference", {})["thinking"] = thinking  # the only per-arm difference
    wiki = os.path.join(_ROOT, "knowledge", "runtime", "wiki")
    return LlmPersona(OllamaInferenceClient(model=doc["inference"]["model"]), lambda: doc,
                      lore=lore, wiki=WikiIndex(wiki), vector=VectorIndex(wiki), tracer=tracer)


def score(tracer, raw_pose, latency, present):
    recs = tracer.recs
    comp = [r for r in recs if r.get("kind") == "generate" and r.get("pass") in (None, "compose")]
    plan = [r for r in recs if r.get("pass") == "plan"]
    raw = comp[-1]["raw_output"] if comp else (raw_pose or "")
    clean = comp[-1]["clean_output"] if comp else (raw_pose or "")
    beat = None
    if plan:
        q = re.findall(r'"([^"]{12,})"', plan[-1].get("clean_output") or "")
        beat = q[0] if q else None
    return {
        "len": len(clean),
        "asterisk": int("*" in raw),
        "voice": int(bool(VOICE.search(clean))),
        "parrot": int(bool(beat) and beat in raw),
        "parrot_elig": int(bool(beat)),
        "names": int(any(n.lower() in clean.lower() for n in present)),
        "latency": latency,
    }


def run_arm(lore, thinking, scenes, nsamples):
    tracer = CapTracer()
    persona = build_persona(lore, thinking, tracer)
    agg = {k: 0 for k in ("asterisk", "voice", "parrot", "parrot_elig", "names")}
    lens, lats, runs = [], [], 0
    for attributed, cut, present in scenes:
        for _ in range(nsamples):
            tracer.reset()
            t0 = time.time()
            pose, _gated = asyncio.run(_generated_pose(persona, attributed, cut))
            lat = time.time() - t0
            s = score(tracer, pose, lat, present)
            for k in agg:
                agg[k] += s[k]
            lens.append(s["len"]); lats.append(lat); runs += 1
    return agg, lens, lats, runs


def main():
    n_scenes = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    nsamples = int(sys.argv[2]) if len(sys.argv) > 2 else 4
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
        present = {s for s, _ in attributed[:cut] if s not in ("scene", "Cricket")}
        scenes.append((attributed, cut, present))
        if len(scenes) >= n_scenes:
            break
    print("scenes=%d samples=%d -> %d runs/arm (seed unset -> distributional)\n"
          % (len(scenes), nsamples, len(scenes) * nsamples))
    for name, thinking in (("A think-ON ", True), ("B think-OFF", False)):
        agg, lens, lats, runs = run_arm(lore, thinking, scenes, nsamples)
        print("%s | voice %2d/%-2d  parrot %2d/%-2d  asterisk %2d/%-2d  names %2d/%-2d  "
              "len med=%3d (min %d)  latency med=%.1fs"
              % (name, agg["voice"], runs, agg["parrot"], agg["parrot_elig"],
                 agg["asterisk"], runs, agg["names"], runs,
                 int(statistics.median(lens)), min(lens), statistics.median(lats)))


if __name__ == "__main__":
    main()
