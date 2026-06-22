"""Model-comparison mechanical panel: current abliterated base vs RP-finetuned bases.

Runs the same corpus scenes through the live persona pointed at each Ollama model, with the
planning pass OFF (the adopted setting) and a per-model starting sampling config (card values --
NOT yet swept; this is a directional read to pick the base, then the winner gets a sampling sweep).
Templates were corrected first (Llama-3 for Lunaris, Mistral [INST] for Rocinante) -- a generic
template silently degrades these tunes, so that fix is a prerequisite for a fair comparison.

Usage: python evals/ab_models.py [n_scenes] [n_samples]
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
from evals.ab_thinking import VOICE, CapTracer  # noqa: E402
from cricket.profiles import ConfigStore  # noqa: E402
from cricket.lore.loader import LoreStore  # noqa: E402
from cricket.lore.vector import VectorIndex  # noqa: E402
from cricket.lore.wiki import WikiIndex  # noqa: E402
from cricket.persona.inference import OllamaInferenceClient  # noqa: E402
from cricket.persona.llm import LlmPersona  # noqa: E402

# (label, ollama model, starting sampling) -- card-recommended starts, not swept.
MODELS = [
    ("current  ", "cricket-abliterated:latest",
     {"temperature": 1.05, "top_p": 1.0, "top_k": 0, "min_p": 0.05, "repeat_penalty": 1.1}),
    ("lunaris-8B", "cricket-lunaris",
     {"temperature": 1.4, "top_p": 1.0, "top_k": 0, "min_p": 0.1, "repeat_penalty": 1.1}),
    ("rocinante12", "cricket-rocinante",
     {"temperature": 1.0, "top_p": 1.0, "top_k": 0, "min_p": 0.1, "repeat_penalty": 1.05}),
]


def build_persona(lore, model, sampling, tracer):
    doc = copy.deepcopy(ConfigStore(os.path.join(_ROOT, "data", "cricket-config.sqlite3")).active()[1])
    inf = doc.setdefault("inference", {})
    inf["model"] = model
    inf["thinking"] = False
    inf.update(sampling)
    wiki = os.path.join(_ROOT, "knowledge", "runtime", "wiki")
    return LlmPersona(OllamaInferenceClient(model=model), lambda: doc,
                      lore=lore, wiki=WikiIndex(wiki), vector=VectorIndex(wiki), tracer=tracer)


def score(tracer, pose, present):
    comp = [r for r in tracer.recs if r.get("kind") == "generate" and r.get("pass") in (None, "compose")]
    raw = comp[-1]["raw_output"] if comp else (pose or "")
    clean = comp[-1]["clean_output"] if comp else (pose or "")
    return {"len": len(clean), "asterisk": int("*" in raw), "voice": int(bool(VOICE.search(clean))),
            "names": int(any(n.lower() in clean.lower() for n in present)), "clean": clean}


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
    print("scenes=%d samples=%d -> %d runs/model (thinking OFF; per-model card sampling, unswept)\n"
          % (len(scenes), nsamples, len(scenes) * nsamples))
    for label, model, sampling in MODELS:
        tracer = CapTracer()
        persona = build_persona(lore, model, sampling, tracer)
        ast = voice = names = runs = 0
        lens, lats, samples_txt = [], [], []
        for attributed, cut, present in scenes:
            for _ in range(nsamples):
                tracer.reset()
                t0 = time.time()
                pose, _g = asyncio.run(_generated_pose(persona, attributed, cut))
                lats.append(time.time() - t0)
                s = score(tracer, pose, present)
                ast += s["asterisk"]; voice += s["voice"]; names += s["names"]
                lens.append(s["len"]); runs += 1
                samples_txt.append(s["clean"])
        print("%s | voice %2d/%-2d  asterisk %2d/%-2d  names %2d/%-2d  len med=%3d (min %d)  lat med=%.1fs"
              % (label, voice, runs, ast, runs, names, runs,
                 int(statistics.median(lens)), min(lens), statistics.median(lats)))
        print("    sample: %r\n" % (next((t for t in samples_txt if t), "")[:170]))


if __name__ == "__main__":
    main()
