"""Round-robin RP generator over the fine-tuned model.

Drives a multi-character scene: each character poses in turn, conditioned on its own
profile sheet plus the running transcript (the same serve-shaped prompt build_finetune
emits). The model's pose is parsed with the XML pose-parser, so puppeting (one character
writing another's pose) is detected and cut.

Round 1 is the "opening" round -- longer, ~3-paragraph poses: the first character sets
the scene (detailed setting description, then their entrance with action + dialogue and
the goal), the others make substantial entrances. Rounds 2..N flow at natural length.

    python tools/rp_roundrobin.py --rounds 10 --chars "Johanna,Bazil,Cricket" \
        --title "Alley Drop" --setting "A lower-level Coruscant alley." \
        --goal "recover an NRI dead-drop before an Imperial courier collects it" \
        --adapter data/finetune/lunaris-rp-full-lora
"""

import argparse
import json
import os
import re
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_finetune as bf
import pose_xml as px

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = open(os.path.join(_ROOT, "data", "finetune", "base_path.txt")).read().strip()
bf.INPUT_BUDGET = 2100


def _system(actor):
    sheet = bf.profile_for(actor)
    s = px.SYSTEM_RULE.format(name=actor) + "\n\n== CHARACTER: %s ==\n" % actor
    return s + (sheet if sheet else "(No profile on file. Infer voice and body from the scene.)")


def _transcript_block(transcript):
    entries = [e for e in (px.render_row(r) for r in transcript) if e]
    return "<transcript>\n" + "\n".join(entries) + "\n</transcript>"


def _opening_messages(meta, actor, transcript, first):
    present = meta["characters"]
    if first:
        instr = ("This is the OPENING pose of the scene. Write about THREE paragraphs. Begin with a "
                 "detailed description of the setting and atmosphere, then bring %s into it with a mix "
                 "of physical action and some dialogue. Establish the situation and the goal." % actor)
    else:
        instr = ("This is your ENTRANCE into the opening scene. Write about three paragraphs -- a mix "
                 "of physical action and some dialogue -- reacting to what has been established so far.")
    head = "Pose as: %s\nScene: %s -- %s\nPresent: %s\n\n%s" % (
        actor, meta["title"], meta["setting"], present, instr)
    user = head + "\n\n" + _transcript_block(transcript)
    return [{"role": "system", "content": _system(actor)},
            {"role": "user", "content": user}]


def _generate(model, tok, msgs, max_new, temp, top_p):
    enc = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt")
    ids = (enc["input_ids"] if hasattr(enc, "keys") else enc).to("cuda")
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=max_new, do_sample=True,
                             temperature=temp, top_p=top_p, pad_token_id=tok.pad_token_id)
    return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--chars", default="Johanna,Bazil,Cricket")
    ap.add_argument("--title", default="Alley Drop")
    ap.add_argument("--setting", default="A lower-level Coruscant alley, deep in the undercity gloom.")
    ap.add_argument("--goal", default="recover an NRI dead-drop datachip before an Imperial courier collects it")
    ap.add_argument("--adapter", default=os.path.join(_ROOT, "data", "finetune", "lunaris-rp-full-lora"))
    ap.add_argument("--base-only", action="store_true")
    ap.add_argument("--max-new", type=int, default=320)
    ap.add_argument("--max-new-open", type=int, default=512)
    ap.add_argument("--temperature", type=float, default=0.85)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    chars = [c.strip() for c in args.chars.split(",") if c.strip()]
    meta = {"title": args.title,
            "setting": args.setting + (" NRI objective: " + args.goal + "." if args.goal else ""),
            "characters": ", ".join(chars)}

    tok = AutoTokenizer.from_pretrained(BASE)
    tok.pad_token = tok.pad_token or tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map="cuda")
    if not args.base_only:
        model = PeftModel.from_pretrained(model, args.adapter)
        print("adapter:", args.adapter)
    model.eval()

    transcript = []                              # rows {type, actor, text}
    verdicts = []
    for rnd in range(args.rounds):
        for ci, actor in enumerate(chars):
            opening = (rnd == 0)
            if opening:
                msgs = _opening_messages(meta, actor, transcript, first=(ci == 0))
                max_new = args.max_new_open
            else:
                sample, _, _ = bf.build_sample(meta, transcript, actor, "")
                msgs = sample["messages"][:-1]
                max_new = args.max_new
            raw = _generate(model, tok, msgs, max_new, args.temperature, args.top_p)
            text, verdict = px.parse_generation(raw, actor)
            if not text.strip():                 # one retry on an empty/garbled parse
                raw = _generate(model, tok, msgs, max_new, args.temperature, args.top_p)
                text, verdict = px.parse_generation(raw, actor)
            verdicts.append(verdict)
            transcript.append({"type": "pose", "actor": actor, "text": text or "(no pose generated)"})
            print("round %2d  %-9s [%s]  %d chars" % (rnd + 1, actor, verdict, len(text)))

    # write outputs
    slug = re.sub(r"[^a-z0-9]+", "-", args.title.lower()).strip("-")
    outdir = os.path.join(_ROOT, "data", "rp_roundrobin")
    os.makedirs(outdir, exist_ok=True)
    md = ["# %s" % args.title, "",
          "*Setting:* %s" % meta["setting"], "",
          "*Cast:* %s   |   *Model:* %s" % (", ".join(chars),
          "base" if args.base_only else os.path.basename(args.adapter)), ""]
    n = 0
    for rnd in range(args.rounds):
        md.append("## Round %d" % (rnd + 1))
        for actor in chars:
            row = transcript[n]; n += 1
            body = row["text"].replace("%t", "    ").replace("%r", "\n")
            md += ["**%s**" % actor, "", body, ""]
    md_path = os.path.join(outdir, slug + ".md")
    open(md_path, "w", encoding="utf-8").write("\n".join(md))
    json.dump({"meta": meta, "chars": chars, "transcript": transcript, "verdicts": verdicts},
              open(os.path.join(outdir, slug + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    import collections
    vc = collections.Counter(verdicts)
    print("\nwrote %d poses -> %s" % (len(transcript), md_path))
    print("pose-parser verdicts:", dict(vc))


if __name__ == "__main__":
    main()
