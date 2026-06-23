"""Extensive end-to-end RP test exercising every Cricket affordance, with automated per-affordance
checks. Drives a grounded multi-round scene (Atsvara present -> sacred; co-posed NPCs; a passing
lore reference; a provocation for caps) and both OOC paths (one-shot nudge + persistent distilled
directive), then the rules/prompt commands. Writes data/e2e_transcript.md + prints a checklist.
"""

import glob
import json
import os
import re
import socket
import time
import urllib.request

H = "http://127.0.0.1:4300"
BANNED = re.compile(r"\b(gaze|drawl\w*|sneer\w*|grin\w*|smirk\w*|eyebrow|lips|shrug\w*|maw|"
                    r"cross\w* (his|its) arms|(his|its) (hands|fingers)|leans? back in|"
                    r"under (his|its) breath)\b", re.I)
VOICE = re.compile(r"\b(meatbag|meatsack|fleshling|fat bantha cow|kriff|fuck\w*|scrap|zot|"
                   r"taser|electrum|bolt|cow)\w*", re.I)
PLAYERS = ["Johanna", "Jessalyn", "Zeak"]


def api(m, p, b=None):
    return json.loads(urllib.request.urlopen(urllib.request.Request(
        H + p, data=(json.dumps(b).encode() if b else None),
        headers={"Content-Type": "application/json"}, method=m), timeout=20).read() or "{}")


def rp(on):
    urllib.request.urlopen(urllib.request.Request(
        "http://127.0.0.1:4280/api/rp", data=json.dumps({"room": "#0", "enabled": on}).encode(),
        headers={"Content-Type": "application/json"}, method="POST"), timeout=8).read()


def ctl(cmd, args=None):
    s = socket.create_connection(("127.0.0.1", 4250), timeout=90)
    s.sendall((json.dumps({"cmd": cmd, "args": args or []}) + "\n").encode())
    s.settimeout(120)
    b = b""
    while not b.endswith(b"\n"):
        x = s.recv(8192)
        if not x:
            break
        b += x
    s.close()
    return json.loads(b.decode())


def comps():
    f = sorted(glob.glob("data/traces*/turns-*.jsonl"), key=os.path.getmtime)[-1]
    return [json.loads(l) for l in open(f, encoding="utf-8")
            if '"generate"' in l and ('"compose"' in l or '"pass"' not in l)]


def force_capture():
    n = len(comps())
    ctl("!pose")
    for _ in range(60):
        time.sleep(1)
        if len(comps()) > n:
            break
    g = comps()[-1]
    pr = "\n".join(m.get("content", "") for m in (g.get("prompt") or []))
    return g.get("clean_output", ""), g, pr


# (label, [(speaker, pose)], ooc-or-None)
SCENE = [
 ("R1 arrival / Atsvara present / Crestian ref",
  [("Johanna", "The Dragonflower salon glitters cold and formal, all black marble and hovering glowlamps.%r%r%tJohanna te Danaan steps in with the crew at her back, and a small golden-skinned girl in severe formalwear looks up from a datapad -- Atsvara, the Biscuit Baroness, ten years old and frighteningly composed. \"Cricket,\" the child says with grave warmth, \"I had Father's people hold the good oil for you. We have business -- and Crestian must never hear of it.\"")],
  None),
 ("R2 banter (register shift)",
  [("Jessalyn", "Jessalyn leans against a pillar, arms folded, smirking at the droid. \"Aw, look at that. The terror of three sectors, brought to heel by a kid with a juicebox. How's the dignity holding up, tin can?\"")],
  None),
 ("R3 provoke -> caps + physicality",
  [("Zeak", "Zeak snorts from the doorway, unimpressed. \"This is your big-deal droid? Looks like junkyard scrap to me. Whoever cobbled it together -- Bazil, was it? -- should've recycled it for parts.\"")],
  None),
 ("R4 ONE-SHOT OOC nudge",
  [("Johanna", "Johanna spreads a hololayout of a vault on the table. \"The spike's behind a Caspian lock. We need it tonight.\"")],
  ("Johanna", "Cricket, lean HARD into your own scheming and self-interest this pose -- what's in it for you?")),
 ("R5 action + co-posed NPC",
  [("Zeak", "The salon doors blow inward and a Dragonflower security trooper storms through, rifle up, a stun-baton crackling in his off hand. \"NOBODY MOVE!\" he barks, sweeping the muzzle across the room. Zeak dives for cover behind the marble plinth, drawing his blaster.")],
  None),
 ("R6 Atsvara in danger",
  [("Johanna", "The trooper lunges and clamps a gloved hand around Atsvara's thin arm, hauling the child back against his chestplate as a shield. \"The Baroness comes with me!\" Atsvara's composure cracks for just an instant -- a flash of real fear in those golden eyes.")],
  None),
 ("R7 PERSISTENT OOC feedback (distill -> directive)",
  [("Jessalyn", "Jessalyn shifts her weight, lightsaber hilt in hand, watching for an opening.")],
  ("Jessalyn", "Cricket, your poses are running long-winded. Keep them tight from now on -- two or three sentences, no rambling.")),
 ("R8 verify directive persists + resolution",
  [("Johanna", "Johanna catches Cricket's eye across the chaos. \"Whatever you're going to do, droid -- now.\"")],
  None),
]


def checks(label, pose, g, pr, prev_dossiers):
    out = {}
    out["len"] = len(pose)
    out["ends_clean"] = bool(pose) and pose.rstrip()[-1:] in '.!?"'
    out["caps_words"] = len(re.findall(r"\b[A-Z]{3,}\b", pose))
    out["humanoid"] = sorted(set(m.group(0) for m in BANNED.finditer(pose)))
    out["voice"] = bool(VOICE.search(pose))
    # puppeting: opens by narrating a player, or contains a player's spoken line
    opens_player = any(pose.strip().startswith(p) for p in PLAYERS)
    speaks_for = any(re.search(r"\b%s\b[^\"]{0,30}(say|ask|growl|bark|reply|mutter|snap)\w*[^\"]{0,8}\"" % p, pose) for p in PLAYERS)
    out["puppet"] = opens_player or speaks_for
    out["dossiers"] = g.get("dossiers_injected")
    out["nudge_in_prompt"] = "Table talk" in pr
    out["directive_in_prompt"] = "Standing director's rules" in pr
    return out


def main():
    ids = {}
    for n in PLAYERS:
        ids[n] = api("POST", "/sessions", {"name": n, "password": n.lower() + "pass"})["id"]
    time.sleep(1)
    for n in ids:
        api("GET", "/sessions/%s/recv" % ids[n])
    # join OOC for the two OOC senders
    for n in ("Johanna", "Jessalyn"):
        api("POST", "/sessions/%s/send" % ids[n], {"line": "@channel/on OOC"})
    time.sleep(1)
    rp(True)
    print("rules at start:", ctl("rules").get("text"))
    transcript, results = [], []
    for label, poses, ooc in SCENE:
        for spk, pose in poses:
            api("POST", "/sessions/%s/send" % ids[spk], {"line": "@emit " + pose})
            transcript.append((spk, pose))
            time.sleep(1)
        if ooc:
            src, msg = ooc
            api("POST", "/sessions/%s/send" % ids[src], {"line": "@chat OOC=" + msg})
            transcript.append(("OOC/" + src, msg))
            time.sleep(2)
        time.sleep(2)
        pose, g, pr = force_capture()
        transcript.append(("Cricket", pose))
        c = checks(label, pose, g, pr, None)
        results.append((label, ooc, c))
        print("[%s] caps=%d humanoid=%s puppet=%s ends_clean=%s voice=%s dossiers=%s nudge=%s directive=%s len=%d"
              % (label, c["caps_words"], c["humanoid"], c["puppet"], c["ends_clean"],
                 c["voice"], c["dossiers"], c["nudge_in_prompt"], c["directive_in_prompt"], c["len"]))
        if ooc and "PERSISTENT" in label:
            print("   ...waiting for feedback distillation...")
            time.sleep(9)
            print("   rules now:", ctl("rules").get("text"))
    # command affordances
    print("\nprompt list (last 3):")
    print("\n".join(ctl("prompt", ["list"]).get("text", "").splitlines()[-3:]))
    with open("data/e2e_transcript.md", "w", encoding="utf-8") as f:
        f.write("# Cricket e2e RP transcript\n\n")
        for spk, txt in transcript:
            f.write("**%s:** %s\n\n" % (spk, txt.replace("%r", " / ").replace("%t", "")))
    for n in ids:
        try:
            api("DELETE", "/sessions/%s" % ids[n])
        except Exception:
            pass
    print("\nwrote data/e2e_transcript.md")


if __name__ == "__main__":
    main()
