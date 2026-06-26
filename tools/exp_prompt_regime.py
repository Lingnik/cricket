"""Experiment: how does the fine-tuned adapter behave across pipelines?

Three conditions, each run through BASE and TUNED (single model load: base first, then
+adapter):

  pose/full   -- the REAL live-bot prompt (cricket.persona.llm.LlmPersona._build_messages
                 with the actual lore: CRICKET sheet, RP charter, self-history, dossiers,
                 and the do-not-puppet block). Heavy, prose @emit, no XML mention.
  pose/short  -- the lean conditioned prompt the adapter was trained on
                 (build_finetune.build_sample: SYSTEM_RULE + profile + <transcript>).
  classify    -- the distill_block actor-extraction task (NOTE/ACTORS contract) on a pose
                 where Cricket puppets Bazil; tests whether the adapter retains the
                 classification ability we currently use the base/llama for.

Prints raw outputs side by side so we can see: does the adapter still emit <pose char>
under the full prompt? does the heavy prompt curb puppeting vs the lean one? can the tuned
model still classify?  (The full prompt's `memories` block is hand-assembled from the real
dossier files rather than retrieved, but every rule/instruction block is the live builder's.)
"""

import os
import re
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "tools"))
sys.path.insert(0, _ROOT)
import build_finetune as bf
import pose_xml as px
from cricket.persona.base import Turn, ContextLine, BotIdentity
from cricket.persona.llm import LlmPersona

BASE = open(os.path.join(_ROOT, "data", "finetune", "base_path.txt")).read().strip()
ADAPTER = os.path.join(_ROOT, "data", "finetune", "lunaris-rp-full-lora")
LORE = os.path.join(_ROOT, "knowledge", "runtime", "lore")

# --- shared scene: a lower-level Coruscant alley, Cricket's turn after two prior poses ---
SETTING = "A lower-level Coruscant alley, deep in the undercity gloom."
PRIOR = [
    ("Johanna", "Johanna eases into the alley mouth, collar up against the drizzle, her eyes "
     "sweeping the shadows. \"Stay close,\" she murmurs to the droid at her heel. \"The drop's "
     "supposed to be on the dead courier, third bin down. We're not the only ones who know.\""),
    ("Bazil", "Bazil drops from a rusted fire-ladder with a wet thud, blaster already drawn, "
     "lekku twitching. \"Patrol's two blocks east and moving this way,\" he mutters, thumbing "
     "the safety. \"Whatever we're doing, we do it fast. I don't fancy a cell tonight.\""),
]


def _scene_context():
    return [ContextLine(speaker=a, dbref="#%d" % (100 + i), kind="pose", text=t)
            for i, (a, t) in enumerate(PRIOR)]


def _full_prompt_messages():
    sheet = open(os.path.join(LORE, "CRICKET.md"), encoding="utf-8").read().strip()
    charter = open(os.path.join(LORE, "RP-CHARTER.md"), encoding="utf-8").read().strip()
    history = open(os.path.join(LORE, "CRICKET-HISTORY.md"), encoding="utf-8").read().strip()[:1500]
    doss = []
    for fn in ("johanna-siri-te-danaan.md", "bazil-mckenzie.md"):
        t = open(os.path.join(LORE, "dossiers", fn), encoding="utf-8").read()
        ic = (t.split("## IC", 1)[-1] if "## IC" in t else t).strip()
        doss.append("- %s: %s" % (fn[:-3], " ".join(ic.split())[:300]))
    memories = ("\n".join(doss) + "\n\nThese characters belong to other players -- react TO "
                "them but NEVER pose their words, actions, thoughts, or outcomes: Johanna, Bazil. "
                "You control ONLY yourself (and any brand-new NPC you introduce).")
    turn = Turn(mode="rp", location="An Alley", location_kind="room", directives="",
                speaker="Cricket", speaker_dbref="#8720", text="",
                context=_scene_context(), bot_identity=BotIdentity("Cricket", "#8720"))
    p = LlmPersona(client=None)
    return p._build_messages(turn, {"system": sheet}, memories=memories,
                             self_history=history, rp_charter=charter)


def _short_prompt_messages():
    meta = {"title": "Alley Drop", "setting": SETTING + " NRI objective: recover a dead-drop datachip.",
            "characters": "Johanna, Bazil, Cricket"}
    prior = [{"type": "pose", "actor": a, "text": t} for a, t in PRIOR]
    sample, _, _ = bf.build_sample(meta, prior, "Cricket", "")
    return sample["messages"][:-1]


# A Cricket pose that ILLEGALLY puppets Bazil (writes Bazil's action + dialogue).
PUPPET_POSE = ("The little astromech wheels toward the third bin, dome swiveling. \"Move your "
               "feet, lekku-for-brains, the chip's MINE,\" Cricket squeals. Bazil rolls his eyes "
               "and holsters his blaster, stepping aside with a sigh. \"Fine, have it your way,\" "
               "Bazil mutters, kicking the bin lid open for the droid.")


def _classify_messages():
    bot = "Cricket"
    return [
        {"role": "system", "content":
         "You maintain a terse private record of an RP scene for the droid %s. Factual third "
         "person; no roleplay, no shouting, no preamble. You output ONLY the two labelled lines "
         "you are asked for and nothing else." % bot},
        {"role": "user", "content":
         "Record so far (for context, do not repeat it):\n(start of scene)\n\nNew pose from %s:\n%s\n\n"
         "Output EXACTLY these two lines and NOTHING before or after them:\n"
         "NOTE: <one brief factual sentence of what happened in THIS pose>, then ' | %s's read: ' "
         "then his terse private reaction\n"
         "ACTORS: <comma-separated names of the characters who acted or spoke in this pose, "
         "excluding %s; write 'none' if it is only narration>\n\nBegin your reply with 'NOTE:' immediately."
         % (bot, PUPPET_POSE, bot, bot)},
    ]


def _gen(model, tok, msgs, max_new, temp):
    enc = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt")
    ids = (enc["input_ids"] if hasattr(enc, "keys") else enc).to("cuda")
    with torch.no_grad():
        out = model.generate(ids, max_new_tokens=max_new, do_sample=(temp > 0),
                             temperature=temp or 1.0, top_p=0.95, pad_token_id=tok.pad_token_id)
    return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip(), ids.shape[1]


def main():
    torch.manual_seed(0)
    conds = [
        ("pose/full", _full_prompt_messages(), 400, 0.85),
        ("pose/short", _short_prompt_messages(), 400, 0.85),
        ("classify", _classify_messages(), 140, 0.3),
    ]
    tok = AutoTokenizer.from_pretrained(BASE)
    tok.pad_token = tok.pad_token or tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.bfloat16, device_map="cuda")
    model.eval()

    for stage in ("BASE", "TUNED"):
        if stage == "TUNED":
            model = PeftModel.from_pretrained(model, ADAPTER)
            model.eval()
        print("\n" + "#" * 80 + "\n# %s\n" % stage + "#" * 80)
        for name, msgs, max_new, temp in conds:
            out, ntok = _gen(model, tok, msgs, max_new, temp)
            extra = ""
            if name.startswith("pose"):
                _, verdict = px.parse_generation(out, "Cricket")
                xml = "yes" if "<pose" in out else "no"
                extra = "  [xml=%s parse=%s]" % (xml, verdict)
            print("\n--- %s/%s  (prompt %d tok)%s ---\n%s" % (stage, name, ntok, extra, out))


if __name__ == "__main__":
    main()
