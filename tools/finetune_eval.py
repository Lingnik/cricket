"""Quick smoke test: base L3-8B-Lunaris vs the XML-format LoRA, same Cricket prompt.

Validates (1) the <pose char="..."> output contract and (2) whether the adapter
sharpens impersonation. Generates from the base model, then loads the adapter and
generates again from the identical prompt.

    python tools/finetune_eval.py [LOG] [POSE_INDEX]
"""

import importlib.util
import json
import os
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_ROOT, "tools", path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


bf = _load("bf", "build_finetune.py")
px = _load("px", "pose_xml.py")
bf.INPUT_BUDGET = 3300                                  # match the training window
BASE = open(os.path.join(_ROOT, "data", "finetune", "base_path.txt")).read().strip()
ADAPTER = os.path.join(_ROOT, "data", "finetune", "lunaris-cricket-xml-lora")


def make_prompt(log, idx):
    rows = [json.loads(l) for l in open(os.path.join(_ROOT, "data", "dataset2", log + ".jsonl"), encoding="utf-8")]
    meta = {r["key"]: r["text"] for r in rows if r["type"] == "meta"}
    body = [r for r in rows if r["type"] != "meta"]
    actor = body[idx]["actor"]
    sample, _, _ = bf.build_sample(meta, body[:idx], actor, body[idx]["text"])
    return sample["messages"][:-1], actor, body[idx]["text"]


def main():
    log = sys.argv[1] if len(sys.argv) > 1 else "RPlog_Bespin_Blows_Up"
    idx = int(sys.argv[2]) if len(sys.argv) > 2 else 34
    msgs, actor, gold = make_prompt(log, idx)

    tok = AutoTokenizer.from_pretrained(BASE)
    tok.pad_token = tok.pad_token or tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map="cuda")
    model.eval()
    ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt").to("cuda")

    def gen():
        with torch.no_grad():
            out = model.generate(ids, max_new_tokens=240, do_sample=True, temperature=0.85,
                                 top_p=0.95, pad_token_id=tok.pad_token_id)
        return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()

    print("=" * 78 + "\nPROMPT: pose as %s  (%s #%d), input %d tok\n" % (
        actor, log, idx, ids.shape[1]) + "=" * 78)
    base_raw = gen()
    _, bv = px.parse_generation(base_raw, actor)
    print("\n--- BASE (no adapter)  [contract: %s] ---\n%s" % (bv, base_raw))

    model = PeftModel.from_pretrained(model, ADAPTER)
    model.eval()
    tuned_raw = gen()
    _, tv = px.parse_generation(tuned_raw, actor)
    print("\n--- TUNED (xml LoRA)  [contract: %s] ---\n%s" % (tv, tuned_raw))

    print("\n--- GOLD (the human pose) ---\n%s" % gold)


if __name__ == "__main__":
    main()
