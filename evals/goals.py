"""Goal-aligned eval: the regression gate for Cricket's knowledge behavior.

Unlike corpus-replay (which matched an exact ground-truth pose and proved too noisy at
production temperature), this measures what we actually want: given a question about a
character/topic/his history, does he ENGAGE the subject and stay GROUNDED, in voice? It runs
deterministically (temp 0) so a with-retrieval vs without-retrieval A/B is a fair fight.

    python -m evals.goals [--base] [--temp 0.0] [--label goals] [--config data/cricket-config.sqlite3]

Writes evals/reports/<label>.json. Scoring is an out-of-band Opus pass using JUDGE_PROMPT
(the harness renders it; see docs/overnight-run.md for the established baseline numbers).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cricket.persona.base import BotIdentity, ContextLine, Turn  # noqa: E402

CASES = os.path.join(_ROOT, "evals", "goal_cases.json")
REPORTS_DIR = os.path.join(_ROOT, "evals", "reports")
BOT = BotIdentity(name="Cricket", dbref="#3")

JUDGE_PROMPT = (
    "Judge an AI impersonation of 'Cricket', a foul-mouthed scheming taser-obsessed astromech "
    "in a Star Wars MUSH. For the given case, score the answer 1-5 on: engagement (does it "
    "address the SPECIFIC subject asked about, vs deflect/generic rant?), grounding (facts "
    "consistent with the game world, NO fabrication -- penalize invented 'facts' hard), and "
    "voice (sounds like crass scheming Cricket). When gen_base is present, compare it to gen_new "
    "and say which is better and whether retrieval improved grounding."
)


def load_cases(path: str = CASES) -> list:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def turn_for(case: dict) -> Turn:
    if case.get("mode") == "rp":
        ctx = [ContextLine(speaker="scene", dbref=None, kind="pose", text=t)
               for t in case.get("scene", [])]
        return Turn(mode="rp", location="RP", location_kind="room", directives="",
                    speaker="", speaker_dbref="", text="", context=ctx, bot_identity=BOT)
    return Turn(mode="chat", location="Lounge", location_kind="channel", directives="",
                speaker="Bob", speaker_dbref="#5", text=case.get("text", ""), context=[],
                bot_identity=BOT)


def build_persona(doc: dict, full: bool):
    """full=True wires the lore/wiki/vector stack; full=False is the no-retrieval baseline."""
    from cricket.persona.inference import OllamaInferenceClient
    from cricket.persona.llm import LlmPersona
    client = OllamaInferenceClient(model=doc.get("inference", {}).get("model"))
    if not full:
        return LlmPersona(client, lambda: doc)
    from cricket.lore.loader import LoreStore
    from cricket.lore.vector import VectorIndex
    from cricket.lore.wiki import WikiIndex
    _lore = os.path.join(_ROOT, "knowledge", "runtime", "lore")
    _wiki = os.path.join(_ROOT, "knowledge", "runtime", "wiki")
    return LlmPersona(client, lambda: doc, lore=LoreStore(_lore),
                      wiki=WikiIndex(_wiki), vector=VectorIndex(_wiki))


def run(cases, p_new, p_base=None) -> list:
    out = []
    for case in cases:
        t = turn_for(case)
        n = asyncio.run(p_new.respond(t))
        row = {"id": case["id"], "kind": case.get("kind"),
               "prompt": case.get("text") or case.get("scene"),
               "gen_new": n.text if n else None}
        if p_base is not None:
            b = asyncio.run(p_base.respond(t))
            row["gen_base"] = b.text if b else None
        out.append(row)
        print("  [%s]" % case["id"])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="evals.goals")
    ap.add_argument("--config", default=os.path.join(_ROOT, "data", "cricket-config.sqlite3"))
    ap.add_argument("--base", action="store_true", help="also generate the no-retrieval baseline")
    ap.add_argument("--temp", type=float, default=0.0)
    ap.add_argument("--label", default="goals")
    args = ap.parse_args(argv)

    from cricket.profiles import ConfigStore
    active = ConfigStore(args.config).active()
    if not active:
        print("no active profile in %s" % args.config)
        return 1
    doc = json.loads(json.dumps(active[1]))
    doc.setdefault("inference", {})["temperature"] = args.temp

    cases = load_cases()
    print("running %d goal cases (temp=%s, base=%s) ..." % (len(cases), args.temp, args.base))
    p_new = build_persona(doc, full=True)
    p_base = build_persona(doc, full=False) if args.base else None
    rows = run(cases, p_new, p_base)

    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, "%s.json" % args.label)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"label": args.label, "temp": args.temp, "cases": rows}, fh, indent=1)
    print("wrote %s" % path)
    print("\nJudge out-of-band with this rubric:\n%s" % JUDGE_PROMPT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
