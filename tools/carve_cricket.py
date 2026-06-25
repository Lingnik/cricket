"""Carve Cricket's embedded spans out of the PRESENT_MINOR logs into a separate
training pool: data/dataset/cricket_embedded.jsonl.

In the older logs Cricket is voiced *inside* another character's pose (almost
always Johanna's). This pulls his own dialogue and the third-person descriptions
of his actions into standalone Cricket poses, each tagged with provenance so it
is never confused with a native pose. Spans are extracted by (start, end) anchor
slicing from the real dataset row text and verified to be exact substrings, so
the carved text is guaranteed verbatim. Other astromechs in these scenes
(Zik's "Shorty", Malign's "Nate", the various "red astromech" units) are
deliberately excluded.

    python tools/carve_cricket.py
"""

import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "dataset")

# (log, source_seq, kind, [(start_anchor, end_anchor), ...])
CARVE = [
 ("RPlog_Fourth_Battle_of_Corellia", 29, "mixed", [
   ("Cricket the homicidal astromech meanwhile", "taste for carnage on a worldwide scale."),
   ('"Don\'t blame me, you fat bantha cow,"', 'A cruise barge?"')]),
 ("RPlog_Fourth_Battle_of_Corellia", 31, "mixed", [
   ('"THEY ARE BLOWING STUFF UP!!"', 'I WISH I HAD NEVER BEEN GIVEN TO YOU!!"')]),
 ("RPlog_Johanna_is_a_Witch", 53, "action", [
   ("Cricket the homicidal R2 astromech sits squarely", "his little holocam at the ready."),
   ("Cricket makes no comment to this,", "befall one Grand Admiral Danik Kreldin.")]),
 ("RPlog_Johanna_is_a_Witch", 57, "action", [
   ("The astromech lets out an ungodly binary shriek", "at an ear-splitting frequency.")]),
 ("RPlog_Motherhood", 17, "mixed", [
   ("From his droid socket, Cricket screams in terror", "WHEN WE BURN TO ASH!!!"),
   ('"At least you got us here in one piece,"', 'try not to kill us in the process?"')]),
 ("RPlog_Motherhood", 23, "mixed", [
   ('"SAVAGES!" Cricket screams at the other droids', '"MAKER-FORSAKEN SAVAGES, ALL!"')]),
 ("RPlog_Motherhood", 28, "mixed", [
   ("From somewhere behind Johanna, Cricket whistles,", '"You are /so/ screwed, kid."')]),
 ("RPlog_Rescue_of_Danik_Kreldin", 40, "action", [
   ("The heap of evil and metal known as Cricket merely zots", "beeps and whistles of dismay and ire")]),
 ("RPlog_Rescue_of_Danik_Kreldin", 59, "action", [
   ("Cricket buzzing furiously", "more and more Imperials approaching.")]),
 ("RPlog_Rescue_of_Danik_Kreldin", 65, "action", [
   ("Cricket's ridiculous shrieks and wails piping shrilly", "organic or electronic,")]),
 ("RPlog_Second_Battle_of_Mon_Calamari_First_Assault", 17, "mixed", [
   ('"Oh it\'s THEM," Cricket bleeps excitedly', 'Today is a good day to die. Don\'t you think?"'),
   ("Cricket finds this insulting and notes", "the Imperial intrusion being a welcome diversion.")]),
 ("RPlog_Second_Battle_of_Mon_Calamari_First_Assault", 21, "mixed", [
   ("Cricket hoots enthusiastically as the targeting computer", "acquires the first ship."),
   ('"You\'ve got him," the droid announces unnecessarily,', '"What are you waiting for!"')]),
 ("RPlog_Second_Battle_of_Mon_Calamari_First_Assault", 31, "mixed", [
   ('"OH WE ARE ALL GOING TO DIE," Cricket wails,', 'YOU STUPID WORTHLESS HUMAN I HATE YOU."')]),
 ("RPlog_Second_Battle_of_Mon_Calamari_First_Assault", 43, "mixed", [
   ('"WHAT THE KARK," the astromech shrieks', 'BAZIL IS GOING TO KILL YOU IF I DIE."')]),
 ("RPlog_Second_Battle_of_Mon_Calamari_First_Assault", 44, "action", [
   ("Immobilizer Five's ministrations towards Rogue Nine are not lost on Cricket,", "her squadmate is being wailed on.")]),
 ("RPlog_Second_Battle_of_Mon_Calamari_First_Assault", 50, "mixed", [
   ('"Oh, my MAKER. YOU FAIL AT LIFE, JOHANNA!" Cricket shrieks irately', "instead of terminating in a pretty, pretty spray.")]),
 ("RPlog_Second_Battle_of_Mon_Calamari_First_Assault", 68, "mixed", [
   ('"Maybe it\'s evil," Cricket idly theorizes', '"Yes. I think it is."')]),
 ("RPlog_Second_Battle_of_Mon_Calamari_First_Assault", 74, "dialogue", [
   ('"I think Zik will be the one to die tonight," Cricket bleeps,', '"He\'s suffered damage."')]),
 ("RPlog_The_Second_Battle_of_Chandrila", 44, "mixed", [
   ('"How about you destroy that big one over there," Cricket bleeps lazily,', 'With the tea and the dinners."')]),
 ("RPlog_The_Second_Battle_of_Chandrila", 54, "mixed", [
   ('"How about the bomber," Cricket suggests,', "I swear the old man is on there!"),
   ('"Really, I bet you he\'s on there," Cricket continues,', '"We should bother him next."')]),
]


def row_text(cache, log, seq):
    if log not in cache:
        cache[log] = {json.loads(l)["seq"]: json.loads(l)
                      for l in open(os.path.join(ROOT, log + ".jsonl"),
                                    encoding="utf-8") if l.strip()}
    return cache[log][seq]


def main():
    cache, out, errors = {}, [], []
    for log, seq, kind, spans in CARVE:
        src = row_text(cache, log, seq)
        src_text = src["text"].replace("%t", "")  # drop wiki indent markers
        host = src.get("actor")
        pieces = []
        for start, end in spans:
            i = src_text.find(start)
            j = src_text.find(end, i + len(start)) if i >= 0 else -1
            if i < 0 or j < 0:
                errors.append(f"{log}#{seq}: anchor not found: {start[:30]!r}..{end[:20]!r}")
                continue
            pieces.append(src_text[i:j + len(end)].strip())
        if pieces:
            out.append({"actor": "Cricket", "kind": kind, "text": "%r".join(pieces),
                        "source_log": log, "source_seq": seq, "host_poser": host,
                        "derived": True})

    if errors:
        print("ANCHOR FAILURES (nothing written):")
        for e in errors:
            print("  -", e)
        raise SystemExit(1)

    for i, r in enumerate(out):
        r2 = {"seq": i}
        r2.update(r)
        out[i] = r2
    path = os.path.join(ROOT, "cricket_embedded.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    kinds = collections_counter(r["kind"] for r in out)
    print(f"wrote {len(out)} carved Cricket poses -> {os.path.relpath(path)}")
    print("by kind:", dict(kinds))
    print("source logs:", len(set(r["source_log"] for r in out)))


def collections_counter(it):
    import collections
    return collections.Counter(it)


if __name__ == "__main__":
    main()
