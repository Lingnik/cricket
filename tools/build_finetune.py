"""Build fine-tuning samples (chat JSONL) from the per-pose dataset.

One sample per target-pose: system (persona-conditioned) + user (tagged, windowed
scene transcript) + assistant (the tagged target pose). Uses tools/pose_xml.py so
the rendered shape is byte-identical to what the live bot will see/emit.

    python tools/build_finetune.py            # writes data/finetune/sample_set.jsonl
"""

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pose_xml as px

LORE = "knowledge/runtime/lore"
DS = "data/dataset2"
INPUT_BUDGET = 15984          # num_ctx 16384 - num_predict 400


def tok(s):
    return round(len(s) / 4)


# Profile resolution: Cricket uses the committed sheet; the top-N characters use the
# generated sheets in data/dataset_full/_profiles/, keyed by player handle. An actor with
# no sheet falls through to the "(no profile -- infer from scene)" path.
import csv
import glob as _glob

_CRICKET = open(os.path.join(LORE, "CRICKET.md"), encoding="utf-8").read().strip()
_PSLUGS = {os.path.basename(f)[:-3]: f for f in _glob.glob("data/dataset_full/_profiles/*.md")}
_VMAP = {}
try:
    for _r in csv.DictReader(open("data/dataset2/name_map.csv", encoding="utf-8")):
        if _r.get("player"):
            _VMAP[_r["variant"]] = _r["player"]
except FileNotFoundError:
    pass


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


_PCACHE = {}


def profile_for(actor):
    """The profile sheet text for a character, or None (no-profile path)."""
    if actor == "Cricket":
        return _CRICKET
    if actor in _PCACHE:
        return _PCACHE[actor]
    cands = []
    h = _VMAP.get(actor)
    if h:
        cands.append(_slug(h))
    toks = actor.split()
    cands += [_slug(toks[0]) if toks else "", _slug(actor)]
    text = None
    for c in cands:
        if c and c in _PSLUGS:
            text = open(_PSLUGS[c], encoding="utf-8").read().strip()
            break
    _PCACHE[actor] = text
    return text


def dossiers_for(present, target):
    """Cricket-POV background; only injected when Cricket is the target (the
    dossiers are written from his perspective)."""
    if target != "Cricket":
        return []
    out = []
    for n in present:
        slug = re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")
        for f in glob.glob(os.path.join(LORE, "dossiers", "*.md")):
            if slug[:10] and slug[:10] in os.path.basename(f):
                txt = open(f, encoding="utf-8").read()
                ic = (txt.split("## IC", 1)[-1] if "## IC" in txt else txt).strip()
                out.append("- %s: %s" % (n, " ".join(ic.split())[:230]))
                break
    return out


def register(prior, target):
    others = [r["text"] for r in prior
              if r.get("type") == "pose" and r.get("actor") not in (target, None, "")]
    avg = sum(len(t) for t in others[-4:]) // min(len(others), 4) if others else 0
    if avg >= 350:
        return "LONG multi-paragraph poses -- match with 2-3 paragraphs of prose."
    if avg >= 150:
        return "a full paragraph with prose around the line."
    return "quick lines -- stay snappy."


def build_sample(meta, prior, actor, text):
    sheet = profile_for(actor)
    system = px.SYSTEM_RULE.format(name=actor) + "\n\n== CHARACTER: %s ==\n" % actor
    system += sheet if sheet else (
        "(No profile on file. Infer this character's voice, manner, and body "
        "from how they act in the scene below.)")
    present = [c.strip() for c in meta.get("characters", "").split(",") if c.strip()]
    doss = dossiers_for(present, actor)
    head = "Pose as: %s\nScene: %s -- %s\nPresent: %s" % (
        actor, meta.get("title", ""), meta.get("setting", ""), ", ".join(present))
    head += ("\n\nBackground you may draw on if it fits (do not info-dump):\n" + "\n".join(doss)
             if doss else "\n\n(No background notes on file for this cast -- read them from the scene.)")
    tail = "\n\nMatch the scene's length and register: " + register(prior, actor)

    # window the transcript: drop oldest entries until system+user fits the budget
    entries = [e for e in (px.render_row(r) for r in prior) if e]
    overhead = tok(system) + tok(head) + tok(tail) + tok("\n\n<transcript>\n\n</transcript>")
    windowed = False
    while entries and overhead + sum(tok(e) + 1 for e in entries) > INPUT_BUDGET:
        entries.pop(0)
        windowed = True
    user = head + "\n\n<transcript>\n" + "\n".join(entries) + "\n</transcript>" + tail
    sample = {"messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
        {"role": "assistant", "content": px.render_target(actor, text)},
    ]}
    return sample, tok(system) + tok(user), windowed


def iter_targets(logs, target_pred):
    """Yield (sample, input_tokens, windowed) for each pose matching target_pred."""
    for name in logs:
        rows = [json.loads(l) for l in open(os.path.join(DS, name + ".jsonl"), encoding="utf-8")]
        meta = {r["key"]: r["text"] for r in rows if r["type"] == "meta"}
        body = [r for r in rows if r["type"] != "meta"]
        for i, r in enumerate(body):
            if r.get("type") == "pose" and r.get("actor") and target_pred(name, r["actor"]):
                yield build_sample(meta, body[:i], r["actor"], r["text"])


def main():
    global INPUT_BUDGET
    INPUT_BUDGET = 2100                       # training window: total < MAXLEN 2560
    logs = sorted(os.path.basename(f)[:-6]
                  for f in _glob.glob(os.path.join(DS, "RPlog_*.jsonl")))
    # every pose across every labeled log is a target (profiled where we have a sheet)
    samples = list(iter_targets(logs, lambda lg, a: True))

    os.makedirs("data/finetune", exist_ok=True)
    out = "data/finetune/train.jsonl"
    with open(out, "w", encoding="utf-8") as fh:
        for s, _, _ in samples:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")

    import collections
    by_char = collections.Counter(s["messages"][2]["content"].split('"', 2)[1] for s, _, _ in samples)
    profiled = sum(1 for s, _, _ in samples
                   if "(No profile on file" not in s["messages"][0]["content"])
    toks = sorted(t for _, t, _ in samples)
    nwin = sum(1 for _, _, w in samples if w)
    print("wrote %d samples (%d logs) -> %s" % (len(samples), len(logs), out))
    print("profiled targets: %d  | no-profile: %d" % (profiled, len(samples) - profiled))
    print("top target characters:", by_char.most_common(12))
    print("input tokens: min %d  median %d  max %d  (budget %d) | windowed %d" % (
        toks[0], toks[len(toks) // 2], toks[-1], INPUT_BUDGET, nwin))


if __name__ == "__main__":
    main()
