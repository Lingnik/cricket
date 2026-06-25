"""Batch generation from base (+ optional LoRA adapter) over a prompts JSONL.

Each input line is {"messages": [...]} -- a chat prompt WITHOUT the final assistant
turn (the shape build_finetune emits, minus the completion), optionally with an
"expect" field naming the target character so the pose-parser can verdict the output.
Each output line echoes the input plus {"generation", "verdict", "parsed"}.

    python tools/infer_batch.py --prompts prompts.jsonl --out gen.jsonl [--adapter DIR | --base-only]
"""

import argparse
import json
import os
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pose_xml as px

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = open(os.path.join(_ROOT, "data", "finetune", "base_path.txt")).read().strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--base-only", action="store_true")
    ap.add_argument("--max-new", type=int, default=400)
    ap.add_argument("--temperature", type=float, default=0.85)
    ap.add_argument("--top-p", type=float, default=0.95)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(BASE)
    tok.pad_token = tok.pad_token or tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map="cuda")
    if args.adapter and not args.base_only:
        model = PeftModel.from_pretrained(model, args.adapter)
        print("loaded adapter:", args.adapter)
    model.eval()

    rows = [json.loads(l) for l in open(args.prompts, encoding="utf-8") if l.strip()]
    n = 0
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            enc = tok.apply_chat_template(r["messages"], add_generation_prompt=True, return_tensors="pt")
            ids = (enc["input_ids"] if hasattr(enc, "keys") else enc).to("cuda")
            with torch.no_grad():
                out = model.generate(ids, max_new_tokens=args.max_new, do_sample=True,
                                     temperature=args.temperature, top_p=args.top_p,
                                     pad_token_id=tok.pad_token_id)
            gen = tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()
            rec = dict(r)
            rec["generation"] = gen
            if r.get("expect"):
                text, verdict = px.parse_generation(gen, r["expect"])
                rec["parsed"], rec["verdict"] = text, verdict
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
            if n % 25 == 0:
                print("...%d/%d" % (n, len(rows)), flush=True)
    print("wrote %d generations -> %s" % (n, args.out))


if __name__ == "__main__":
    main()
