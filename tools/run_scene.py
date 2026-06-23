"""Drive a 7-round action RP scene through the harness and capture the full transcript.

A data-spike heist on the Caspian customs docks that goes loud: stakes grounded in the dossiers
(the spike implicates Atsvara -> Cricket's beloved Baroness; Crestian's "embarrass the family and
get recycled for scrap"; Johanna his 25-year owner takes a hit). Tests thread continuity + action.
Writes data/scene_transcript.md for the corpus-critique agent.
"""

import glob
import json
import os
import socket
import time
import urllib.request

H = "http://127.0.0.1:4300"


def api(method, path, body=None):
    req = urllib.request.Request(H + path, data=(json.dumps(body).encode() if body else None),
                                 headers={"Content-Type": "application/json"}, method=method)
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or "{}")


def rp(on):
    urllib.request.urlopen(urllib.request.Request(
        "http://127.0.0.1:4280/api/rp", data=json.dumps({"room": "#0", "enabled": on}).encode(),
        headers={"Content-Type": "application/json"}, method="POST"), timeout=8).read()


def force_pose():
    s = socket.create_connection(("127.0.0.1", 4250), timeout=60)
    s.sendall(b'{"cmd":"!pose","args":[]}\n')
    s.settimeout(90)
    b = b""
    while not b.endswith(b"\n"):
        x = s.recv(4096)
        if not x:
            break
        b += x
    s.close()


def _tracef():
    return sorted(glob.glob("data/traces*/turns-*.jsonl"), key=os.path.getmtime)[-1]


def composes():
    g = [json.loads(l) for l in open(_tracef(), encoding="utf-8") if '"generate"' in l]
    return [x for x in g if x.get("pass") in (None, "compose")]


ROUNDS = [
 ("R1 setup", [
  ("Johanna", "Rain sheets off the corrugated roofs of the Caspian customs docks, hammering the puddled permacrete as Johanna te Danaan leads them into the lee of a stacked cargo container.%r%r%tShe wipes the water from her eyes and jerks her chin at the warehouse blast door, its access panel glowing a sullen amber. \"The data-spike is inside, in a Dragonflower lockbox. It puts Atsvara's name on the Biscuit Baron sabotage. If Crestian's people pull it before we do, that little Baroness is finished, and so is every droid she has ever owned.\" She crouches by the panel and slaps it. \"Cricket. The lock. Make it quiet.\""),
 ]),
 ("R2 complication", [
  ("Jessalyn", "Jessalyn presses to the corner of the container, rain plastering her red hair flat, one hand loose at her blaster.%r%r%t\"Make it fast,\" she murmurs, watching the far end of the gantry. \"Two Dragonflower troopers just turned onto the dock, and they are not strolling. Somebody tripped a passive sensor.\""),
  ("Zeak", "Zeak thumbs the safety off his carbine and sinks deeper into the shadow of the cargo stack, jaw tight. \"Whatever you are doing in there, droid, do it now.\""),
 ]),
 ("R3 the drone", [
  ("Johanna", "The blast door grinds back and Johanna is through it before it is fully open, boots skidding on the wet floor.%r%r%tThe lockbox sits on a shelf at the back, but a Dragonflower security drone unfolds from the ceiling with a whine of servos, its spotlight swinging toward them, a warning klaxon already building in its throat. Johanna lunges for the box. \"CRICKET. The drone. Before it broadcasts!\""),
 ]),
 ("R4 firefight", [
  ("Zeak", "Too late. The klaxon shrieks out across the dock, and the first Dragonflower trooper rounds the door with his rifle up.%r%r%tZeak pivots out of cover and puts a bolt into the man's shoulder, spinning him into the doorframe. \"They know we are here! Move!\" A second trooper opens up from the gantry, blasterfire stitching molten holes across the cargo containers."),
 ]),
 ("R5 crisis", [
  ("Johanna", "Johanna twists the lockbox open, snatches the data-spike, and a blaster bolt catches her across the ribs, slamming her into the shelving with a grunt of pain. The spike skitters from her fingers across the wet floor.%r%r%tShe is down on one knee, blood at her side, the troopers closing. \"The spike,\" she gasps, reaching, too slow. \"Don't let them have it.\" Another bolt cracks overhead."),
 ]),
 ("R6 the turn", [
  ("Jessalyn", "Jessalyn is through the door in a blur, lightsaber snapping to life in a column of green, batting a bolt back into the lead trooper's chest.%r%r%t\"I have Joh. You get her clear!\" She plants herself between the wounded warlord and the gantry, deflecting fire in a sizzling arc. \"Whatever that little monster just pulled, it bought us seconds. USE them.\""),
 ]),
 ("R7 escape", [
  ("Johanna", "They spill out into the rain, the blast door grinding shut behind them on the droid's command, sealing the troopers inside. Johanna sags against the cargo stack, one hand pressed to her bleeding side, the data-spike clenched white-knuckled in the other.%r%r%tShe looks down at the little astromech, rain streaming off his dome, and lets out a breathless, pained laugh. \"Twenty-five years, you rusted little terror, and you still only move that fast when it is your own neck.\" She tucks the spike away. \"Atsvara owes you a taser upgrade for this one.\""),
 ]),
]


def main():
    ids = {}
    for n, pw in [("Johanna", "johannapass"), ("Jessalyn", "jessalynpass"), ("Zeak", "zeakpass")]:
        ids[n] = api("POST", "/sessions", {"name": n, "password": pw})["id"]
    time.sleep(1)
    for n in ids:
        api("GET", "/sessions/%s/recv" % ids[n])
    rp(True)
    transcript = []
    for label, poses in ROUNDS:
        for spk, pose in poses:
            api("POST", "/sessions/%s/send" % ids[spk], {"line": "@emit " + pose})
            transcript.append((spk, pose))
            time.sleep(1)
        time.sleep(2)
        before = len(composes())
        force_pose()
        for _ in range(50):
            time.sleep(1)
            if len(composes()) > before:
                break
        cpose = composes()[-1].get("clean_output") or "(no pose)"
        transcript.append(("Cricket", cpose))
        print("[%s] Cricket: %s" % (label, cpose[:110]))
    with open("data/scene_transcript.md", "w", encoding="utf-8") as f:
        f.write("# Live RP scene transcript (cricket-lunaris) -- 7-round data-spike heist\n\n")
        for spk, txt in transcript:
            f.write("**%s:** %s\n\n" % (spk, txt.replace("%r", " / ").replace("%t", "")))
    for n in ids:
        try:
            api("DELETE", "/sessions/%s" % ids[n])
        except Exception:
            pass
    print("wrote data/scene_transcript.md (%d poses)" % len(transcript))


if __name__ == "__main__":
    main()
