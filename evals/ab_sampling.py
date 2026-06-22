"""A/B mechanical-metric harness for sampling configs (small-model RP).

Replays REAL captured compose prompts (from the turn trace) through Ollama under several sampling
configs x seeds, and scores the countable defects the prompt sample exhibited -- so sampling is
tuned from distributions, not a single anecdote. Metrics:
  - asterisk : raw output contains '*' (markdown action-beat leak; instruction said none)
  - parrot   : raw output reproduces, verbatim, a quoted "beat" from the injected plan -- tracked
               as its OWN metric because repeat_penalty can MASK the symptom without fixing the
               planner-level bug (only counted over prompts whose plan actually has a quoted beat)
  - len      : cleaned-output length (terseness)
  - voice    : cleaned output hits a crass/in-character voice marker

Usage: python evals/ab_sampling.py [n_prompts] [n_seeds]
"""

import glob
import json
import os
import re
import statistics
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cricket.persona.llm import _clean_output  # noqa: E402

OLLAMA = "http://127.0.0.1:11434/api/chat"
MODEL = "cricket-abliterated:latest"

CONFIGS = {
    "current": {"temperature": 0.85, "top_p": 0.95},
    "rp":      {"temperature": 1.05, "top_p": 1.0, "top_k": 0, "min_p": 0.05,
                "repeat_penalty": 1.1, "repeat_last_n": 256},
    "rp_warm": {"temperature": 1.2, "top_p": 1.0, "top_k": 0, "min_p": 0.06,
                "repeat_penalty": 1.1, "repeat_last_n": 256},
    "rp_ctrl": {"temperature": 1.0, "top_p": 1.0, "top_k": 0, "min_p": 0.1,
                "repeat_penalty": 1.15, "repeat_last_n": 384},
}
VOICE = re.compile(r"\b(meatbag|scrap|bolt|fat|idiot|fool|moron|rust|grease|kriff|stupid|"
                   r"zot|slag|junk|worthless|pathetic|spineless)\w*", re.I)


def _latest_trace():
    files = sorted(glob.glob("data/traces*/turns-*.jsonl"), key=os.path.getmtime)
    return files[-1] if files else None


def load_prompts(n):
    recs = [json.loads(l) for l in open(_latest_trace(), encoding="utf-8")]
    comp = [r for r in recs if r.get("kind") == "generate" and r.get("prompt")
            and r.get("pass") in (None, "compose")]
    out = []
    for r in comp:
        text = "\n".join(m["content"] for m in r["prompt"])
        m = re.search(r"private plan.*", text, re.S | re.I)
        beats = re.findall(r'"([^"]{15,})"', m.group(0)[:700]) if m else []
        out.append({"msgs": r["prompt"], "beat": beats[0] if beats else None})
    return out[-n:]


def gen(msgs, opts, seed):
    body = {"model": MODEL, "messages": msgs, "stream": False,
            "options": dict(opts, seed=seed, num_predict=220)}
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=120).read())["message"]["content"]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    nseeds = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    prompts = load_prompts(n)
    elig = sum(1 for p in prompts if p["beat"])
    print("prompts=%d (parrot-eligible=%d) seeds=%d -> %d runs/config\n"
          % (len(prompts), elig, nseeds, len(prompts) * nseeds))
    for cname, opts in CONFIGS.items():
        ast = par = par_elig = voice = 0
        lens = []
        for p in prompts:
            for s in range(1, nseeds + 1):
                raw = gen(p["msgs"], opts, s)
                clean = _clean_output(raw, "rp")
                ast += int("*" in raw)
                if p["beat"]:
                    par_elig += 1
                    par += int(p["beat"] in raw)
                voice += int(bool(VOICE.search(clean)))
                lens.append(len(clean))
        runs = len(lens)
        print("%-8s | asterisk %2d/%-2d  parrot %2d/%-2d  voice %2d/%-2d  "
              "len med=%3d (min %d, max %d)"
              % (cname, ast, runs, par, par_elig, voice, runs,
                 int(statistics.median(lens)), min(lens), max(lens)))


if __name__ == "__main__":
    main()
