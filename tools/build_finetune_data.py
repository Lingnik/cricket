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


def _example(persona, prompts, self_hist, charter, ctx_lines, target, tag):
    ctx = _tail([cl for cl in ctx_lines if cl.text])
    if not ctx:
        return None
    turn = Turn(speaker=ctx[-1].speaker, speaker_dbref=None, text=ctx[-1].text, mode="rp",
                location=ROOM, location_kind=ROOM_KIND, directives="", context=ctx)
    memories = persona._retrieve_memories(turn)
    msgs = persona._build_messages(turn, prompts, memories, plan="", thinking=False,
                                   self_history=self_hist, rp_charter=charter)
    msgs.append({"role": "assistant", "content": target})
    return {"log": tag, "messages": msgs}


def _ctx_before(rows, seq):
    """ContextLines for scene/pose rows strictly before `seq` in a source log."""
    out = []
    for r in sorted(rows, key=lambda r: r.get("seq", 0)):
        if r.get("seq", 0) >= seq or r.get("type") not in ("scene", "pose"):
            continue
        t = _norm(r.get("text"))
        if t:
            out.append(ContextLine(speaker=(r.get("actor") or "scene"), dbref=None,
                                   kind=("pose" if r.get("type") == "pose" else "emit"), text=t))
    return out


def main():
    persona, doc = _persona()
    prompts = doc.get("prompts", {})
    self_hist = persona._lore.self_history() if persona._lore else ""
    charter = persona._lore.rp_charter() if persona._lore else ""
    examples = []
    # (a) standalone Cricket pose rows across the per-log corpus
    log_cache = {}
    for f in sorted(glob.glob(os.path.join(_ROOT, "data", "dataset", "RPlog_*.jsonl"))):
        rows = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
        log_cache[os.path.splitext(os.path.basename(f))[0]] = rows
        turns = _turns(rows)
        for i, (spk, kind, text, is_cric) in enumerate(turns):
            if not (is_cric and text) or i == 0:
                continue
            ctx = [ContextLine(speaker=s, dbref=None, kind=k, text=t) for s, k, t, _ in turns[:i]]
            ex = _example(persona, prompts, self_hist, charter, ctx, text, os.path.basename(f))
            if ex:
                examples.append(ex)
    # (b) Cricket poses embedded inside other players' poses -- context rebuilt from the source log
    emb = os.path.join(_ROOT, "data", "dataset", "cricket_embedded.jsonl")
    for r in (json.loads(l) for l in open(emb, encoding="utf-8") if l.strip()) if os.path.exists(emb) else []:
        if str(r.get("actor", "")).lower() != "cricket":
            continue
        target = _norm(r.get("text"))
        src = log_cache.get(r.get("source_log"))
        if not (target and src):
            continue
        ex = _example(persona, prompts, self_hist, charter,
                      _ctx_before(src, r.get("source_seq", 0)), target, "embedded")
        if ex:
            examples.append(ex)
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
