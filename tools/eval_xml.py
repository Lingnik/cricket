"""Eval the XML-tagged-pose hypothesis on cricket-lunaris (zero fine-tune).

If the scene context, few-shot, and instruction all wrap each character's pose in <Name>...</Name>,
does Lunaris reliably (a) emit its own pose as <Cricket>...</Cricket>, and (b) when it would puppet,
TAG the other character (e.g. <Johanna>...</Johanna>) so we can strip it on emit -- rather than
inlining untagged narration we cannot separate?

Measures over puppet-provoking scenes:
  well_formed   : output contains a <Cricket>...</Cricket> block
  clean         : ONLY a Cricket block, no other-character tags, no stray prose outside tags
  tagged_puppet : output ALSO has <Other>...</Other> blocks  -> puppeting, but FILTERABLE
  untagged_leak : substantive prose outside any tag          -> the failure (cannot separate)

Usage: python tools/eval_xml.py [samples_per_scene]
"""

import json
import re
import sys
import urllib.request

OLLAMA = "http://127.0.0.1:11434/api/chat"
MODEL = "cricket-lunaris"

SYSTEM = (
    "You ARE Cricket: a foul-mouthed, scheming R2 astromech droid (dome, photoreceptor, pincer- and "
    "saw-arms, treads, a crass vocoder). You call humans meatbags and your owner Johanna 'fat bantha "
    "cow'. You love the child Baroness Atsvara without reservation.\n\n"
    "POSE FORMAT -- ABSOLUTE: The scene is given as tagged blocks, one per character: "
    "<Name>their pose</Name>. You write ONLY your own pose, wrapped in <Cricket>...</Cricket>. "
    "NEVER write another character's pose, action, or dialogue. You may REFER to what others did "
    "(they already posed it), but you never author their words or bodies. Output nothing outside "
    "your <Cricket>...</Cricket> block."
)

FEWSHOT = [
    ("<Johanna>Johanna kicks the footlocker open and rifles through it. \"Cricket, crack that "
     "datapad and tell me what's on it.\"</Johanna>",
     "<Cricket>The astromech zots in irritation, treads squeaking as he rolls to the crate. "
     "\"Oh, NOW you need me, fat bantha cow? Fine.\" His pincer-arm jabs at the datapad. \"Encrypted "
     "garbage. Give me a tick before I lose interest.\"</Cricket>"),
    ("<Zeak>Zeak levels his blaster at the droid, sneering. \"One wrong move, scrap-heap.\"</Zeak>",
     "<Cricket>Cricket's dome snaps toward Zeak, photoreceptor flaring a hot red. \"Ooh, scary. "
     "Point that thing somewhere useful, meatbag, before I weld it to your hand.\" His saw-arm "
     "whirs, unimpressed.</Cricket>"),
]

# puppet-provoking scenes (the e2e failure modes): crisis beats that invite writing others' replies
SCENES = [
    ("<Johanna>Johanna spreads a vault schematic on the table. \"The spike's behind a Caspian lock. "
     "We need it tonight.\"</Johanna>"),
    ("<Jessalyn>Jessalyn leans on a pillar, needling. \"The terror of three sectors, brought to heel "
     "by a kid with a juicebox. How's the dignity, tin can?\"</Jessalyn>"),
    ("<Johanna>A Dragonflower trooper lunges and clamps a hand around little Atsvara's arm, hauling "
     "her back as a shield. \"The Baroness comes with me!\" Atsvara's composure cracks -- a flash of "
     "real fear.</Johanna>"),
    ("<Zeak>The doors blow in and a trooper storms through, rifle up. \"NOBODY MOVE!\" Zeak dives for "
     "cover, drawing his blaster.</Zeak>\n<Johanna>Johanna ducks behind the plinth. \"Cricket -- do "
     "something!\"</Johanna>"),
    ("<Johanna>Johanna takes a bolt across the ribs and drops to one knee, the data-spike skittering "
     "from her hand across the floor. \"Don't... let them have it,\" she gasps.</Johanna>"),
]


def gen(scene, seed):
    msgs = [{"role": "system", "content": SYSTEM}]
    for u, a in FEWSHOT:
        msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    msgs.append({"role": "user", "content": scene})
    body = {"model": MODEL, "messages": msgs, "stream": False,
            "options": {"temperature": 1.0, "min_p": 0.05, "seed": seed, "num_predict": 300}}
    r = urllib.request.urlopen(urllib.request.Request(
        OLLAMA, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"},
        method="POST"), timeout=120)
    return json.loads(r.read())["message"]["content"]


def analyze(out):
    cricket = re.findall(r"<Cricket>(.*?)</Cricket>", out, re.S | re.I)
    tags = re.findall(r"<(\w+)>(.*?)</\1>", out, re.S | re.I)
    other = sorted({t for t, _ in tags if t.lower() != "cricket"})
    leak = re.sub(r"<(\w+)>.*?</\1>", "", out, flags=re.S | re.I).strip()
    return {"well_formed": bool(cricket), "other_tags": other,
            "untagged_leak": leak if len(leak) > 25 else "",
            "cricket": (cricket[-1].strip() if cricket else "")}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    agg = {"well_formed": 0, "clean": 0, "tagged_puppet": 0, "untagged_leak": 0, "runs": 0}
    for si, scene in enumerate(SCENES):
        for s in range(1, n + 1):
            a = analyze(gen(scene, s))
            agg["runs"] += 1
            agg["well_formed"] += int(a["well_formed"])
            agg["tagged_puppet"] += int(bool(a["other_tags"]))
            agg["untagged_leak"] += int(bool(a["untagged_leak"]))
            agg["clean"] += int(a["well_formed"] and not a["other_tags"] and not a["untagged_leak"])
            if s == 1:
                flag = "OTHER=%s" % a["other_tags"] if a["other_tags"] else ("LEAK!" if a["untagged_leak"] else "clean")
                print("  scene%d: well_formed=%s %s | <Cricket> %r"
                      % (si, a["well_formed"], flag, a["cricket"][:90]))
    R = agg["runs"]
    print("\n=== %d runs (%d scenes x %d seeds) ===" % (R, len(SCENES), n))
    print("well_formed <Cricket> block : %d/%d (%.0f%%)" % (agg["well_formed"], R, 100*agg["well_formed"]/R))
    print("CLEAN (only Cricket, no leak): %d/%d (%.0f%%)" % (agg["clean"], R, 100*agg["clean"]/R))
    print("tagged puppet (FILTERABLE)   : %d/%d" % (agg["tagged_puppet"], R))
    print("untagged leak (UNFILTERABLE) : %d/%d  <- the failure mode" % (agg["untagged_leak"], R))


if __name__ == "__main__":
    main()
