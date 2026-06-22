"""Quick A/B of the LoRA adapter vs the base Lunaris on a few training prompts.

Loads base (bf16) once and toggles the adapter on/off to generate the same prompt both ways, so
we can see what the fine-tune changed -- and a verbatim-overlap check against the gold pose flags
the small-corpus memorization/overfit failure the design doc warns about.

  python tools/test_adapter.py [n]
"""

import json
import os
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = open(os.path.join(_ROOT, "data", "finetune", "base_path.txt")).read().strip()
ADAPTER = os.path.join(_ROOT, "data", "finetune", "lunaris-cricket-lora")
GENLEN, PROMPT_CAP = 200, 2360


def overlap(gen, gold):
    """Fraction of generated 8-grams that appear verbatim in the gold pose (memorization signal)."""
    g, h = gen.split(), set()
    for i in range(len(gold.split()) - 7):
        h.add(" ".join(gold.split()[i:i + 8]))
    hits = sum(1 for i in range(len(g) - 7) if " ".join(g[i:i + 8]) in h)
    return hits / max(1, len(g) - 7)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map="cuda")
    model = PeftModel.from_pretrained(model, ADAPTER)
    model.eval()
    rows = [json.loads(l) for l in open(os.path.join(_ROOT, "data", "finetune", "train.jsonl"), encoding="utf-8")]
    for r in rows[:n]:
        msgs, gold = r["messages"][:-1], r["messages"][-1]["content"]
        ids = tok.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True)
        if hasattr(ids, "input_ids"):
            ids = ids["input_ids"]
        if ids and isinstance(ids[0], (list, tuple)):
            ids = ids[0]
        ids = ids[-PROMPT_CAP:]
        inp = torch.tensor([ids], device="cuda")

        def gen():
            with torch.no_grad():
                out = model.generate(inp, max_new_tokens=GENLEN, do_sample=True, temperature=1.0,
                                     top_p=0.95, repetition_penalty=1.1, pad_token_id=tok.eos_token_id)
            return tok.decode(out[0][len(ids):], skip_special_tokens=True).strip()

        tuned = gen()
        with model.disable_adapter():
            base = gen()
        print("=" * 80)
        print("BASE  :", base[:300])
        print("TUNED :", tuned[:300])
        print("GOLD  :", gold[:160])
        print("tuned 8-gram overlap w/ gold: %.1f%%" % (100 * overlap(tuned, gold)))


if __name__ == "__main__":
    main()
