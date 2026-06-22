"""Carve the structured RP-log corpus into QLoRA training examples.

For each log, every Cricket pose becomes ONE example: the scene-so-far (all prior scene/pose turns,
tail-trimmed to the runtime byte budget) is run through the LIVE persona prompt builder
(_retrieve_memories + _build_messages) so the prompt is format-identical to inference, and Cricket's
actual pose is the assistant completion. Few-shot is stripped (the fine-tune replaces it). A log
with N Cricket turns yields N examples (partial-through-full scene context).

  python tools/build_finetune_data.py        -> writes data/finetune/train.jsonl
"""

import copy
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cricket.persona.base import Turn, ContextLine  # noqa: E402
from cricket.persona.llm import LlmPersona  # noqa: E402
from cricket.profiles import ConfigStore  # noqa: E402
from cricket.lore.loader import LoreStore  # noqa: E402
from cricket.lore.vector import VectorIndex  # noqa: E402
from cricket.lore.wiki import WikiIndex  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOM, ROOM_KIND = "#0", "room"
CTX_BYTES = 6000  # match the runtime rp_context_bytes tail budget


def _persona():
    doc = copy.deepcopy(ConfigStore(os.path.join(_ROOT, "data", "cricket-config.sqlite3")).active()[1])
    doc.setdefault("prompts", {})["fewshot"] = []   # fine-tune replaces few-shot
    wiki = os.path.join(_ROOT, "knowledge", "runtime", "wiki")
    p = LlmPersona(None, lambda: doc, lore=LoreStore(os.path.join(_ROOT, "knowledge", "runtime", "lore")),
                   wiki=WikiIndex(wiki), vector=VectorIndex(wiki))
    return p, doc


def _norm(text):
    t = (text or "").strip()
    while t[:2] in ("%t", "%r"):
        t = t[2:].lstrip()
    return t


def _turns(rows):
    """Ordered (speaker, kind, text) for scene + pose rows; meta/desc dropped."""
    out = []
    for r in sorted(rows, key=lambda r: r.get("seq", 0)):
        ty = r.get("type")
        if ty == "pose":
            out.append((r.get("actor") or "?", "pose", _norm(r.get("text")), bool(str(r.get("actor", "")).lower() == "cricket")))
        elif ty == "scene":
            out.append(("scene", "emit", _norm(r.get("text")), False))
    return out


def _tail(ctx_lines):
    kept, total = [], 0
    for cl in reversed(ctx_lines):
        total += len(cl.text)
        kept.append(cl)
        if total >= CTX_BYTES:
            break
    return list(reversed(kept))


def main():
    persona, doc = _persona()
    prompts = doc.get("prompts", {})
    self_hist = persona._lore.self_history() if persona._lore else ""
    charter = persona._lore.rp_charter() if persona._lore else ""
    examples = []
    for f in sorted(glob.glob(os.path.join(_ROOT, "data", "dataset", "RPlog_*.jsonl"))):
        rows = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
        turns = _turns(rows)
        for i, (spk, kind, text, is_cric) in enumerate(turns):
            if not (is_cric and text):
                continue
            prior = turns[:i]
            if not prior:
                continue
            ctx = _tail([ContextLine(speaker=s, dbref=None, kind=k, text=t) for s, k, t, _ in prior if t])
            last = ctx[-1]
            turn = Turn(speaker=last.speaker, speaker_dbref=None, text=last.text, mode="rp",
                        location=ROOM, location_kind=ROOM_KIND, directives="", context=ctx)
            memories = persona._retrieve_memories(turn)
            msgs = persona._build_messages(turn, prompts, memories, plan="", thinking=False,
                                           self_history=self_hist, rp_charter=charter)
            msgs.append({"role": "assistant", "content": text})
            examples.append({"log": os.path.basename(f), "messages": msgs})
    out = os.path.join(_ROOT, "data", "finetune", "train.jsonl")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")
    chars = [sum(len(m["content"]) for m in ex["messages"]) for ex in examples]
    print("wrote %s: %d examples" % (out, len(examples)))
    print("prompt+target chars: median=%d max=%d" % (sorted(chars)[len(chars) // 2], max(chars)))


if __name__ == "__main__":
    main()
