"""Scene replay: take a real multi-party RP log, feed the lead-up to a Cricket pose through
the FULL RP stack (block grouping -> per-block ledger -> dossiers/shared-history/do-not-puppet
-> _trigger_rp), and print the pose Cricket generates NEXT beside what he actually did.

Unlike corpus-replay (a 3-line window), this reconstructs the whole scene-so-far with best-guess
speaker attribution from the gazetteer (narration -> 'scene'), so the new RP machinery exercises.

    python -m evals.scene_replay [--log corpus/wiki/<file>.txt] [--cut N] [--list]

These wiki logs are edited prose, not raw pose streams, so attribution is heuristic.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cricket.commands import builtins  # noqa: E402
from cricket.commands.registry import CommandContext  # noqa: E402
from cricket.auth import Level  # noqa: E402
from cricket.lore.loader import LoreStore  # noqa: E402
from cricket.lore.vector import VectorIndex  # noqa: E402
from cricket.lore.wiki import WikiIndex  # noqa: E402
from cricket.mush.events import Actor, RoomMessage, SpeechKind  # noqa: E402
from cricket.persona.base import BotIdentity  # noqa: E402
from cricket.profiles import ConfigStore  # noqa: E402
from cricket.router import Router  # noqa: E402
from evals.replay import is_cricket_pose, paragraphs  # noqa: E402

ROOM = "#rp"


class _CapturingActions:
    """Records whatever the pose machinery emits (the generated pose, or a consent request)."""

    def __init__(self):
        self.calls = []

    def _rec(self, kind, *a):
        self.calls.append((kind,) + a)
        return True

    def pose_room(self, text):
        return self._rec("pose", text)

    def emit_room(self, text):
        return self._rec("emit", text)

    def say_room(self, text):
        return self._rec("say", text)

    def say_channel(self, ch, text):
        return self._rec("say_channel", ch, text)

    def page(self, target, text):
        return self._rec("page", target, text)


def attribute(paras, lore):
    """Best-guess (speaker, text) per paragraph: the known character whose name appears earliest
    near the start is the actor; otherwise it is narration ('scene')."""
    out = []
    for p in paras:
        names = lore.mentioned(p, max_names=6)
        best, best_pos = None, 10 ** 9
        low = p.lower()
        for n in names:
            pos = low.find(n.split()[0].lower())
            if 0 <= pos < best_pos:
                best, best_pos = n, pos
        speaker = best if (best is not None and best_pos <= 40) else "scene"
        out.append((speaker, p))
    return out


def cut_points(attributed):
    """Indices of Cricket poses with at least 2 distinct non-Cricket/non-scene prior speakers."""
    pts = []
    for i, (spk, text) in enumerate(attributed):
        if i == 0 or not is_cricket_pose(text):
            continue
        prior = {s for s, _ in attributed[:i] if s not in ("scene", "Cricket")}
        if len(prior) >= 2:
            pts.append((i, sorted(prior)))
    return pts


def make_bot(persona):
    from types import SimpleNamespace
    from cricket.memory.store import MemoryStore
    return SimpleNamespace(
        current_room=ROOM, current_room_desc="", rp_enabled={ROOM: True},
        scene_queues={}, scene_ledger={}, scene_owners={}, suggestions={},
        pending_consent={}, consent_granted={}, pending_recall={}, recent={}, muted=False,
        persona=persona, bot_identity=BotIdentity("Cricket", "#3"), actions=_CapturingActions(),
        locations={}, store=MemoryStore(":memory:"), memory=None, active_profile_doc=None,
    )


async def replay(persona, attributed, cut):
    bot = make_bot(persona)
    router = Router(bot)
    bot.router = router
    dbrefs, nxt = {}, [100]

    def dbref_for(name):
        if name in ("scene", "Cricket"):
            return None
        if name not in dbrefs:
            dbrefs[name] = "#%d" % nxt[0]
            nxt[0] += 1
        return dbrefs[name]

    for spk, text in attributed[:cut]:
        await router.handle(RoomMessage(Actor(spk, dbref_for(spk)), SpeechKind.POSE, text))
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending)
    ctx = CommandContext(source="mush", level=Level.ADMIN, reply=lambda m: None, bot=bot)
    await builtins._trigger_rp(ctx, ROOM, force_action="pose")
    return bot


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="evals.scene_replay")
    ap.add_argument("--log", default=None)
    ap.add_argument("--cut", type=int, default=None)
    ap.add_argument("--window", type=int, default=12, help="prior paragraphs to show")
    ap.add_argument("--list", action="store_true", help="list candidate cut points and exit")
    args = ap.parse_args(argv)

    log = args.log
    if not log:
        cands = sorted(glob.glob(os.path.join(_ROOT, "corpus", "wiki", "2024*Droid*")))
        log = cands[0] if cands else sorted(glob.glob(os.path.join(_ROOT, "corpus", "wiki", "*.txt")))[0]
    lore = LoreStore(os.path.join(_ROOT, "lore"))
    paras = paragraphs(open(log, encoding="utf-8", errors="replace").read())
    attributed = attribute(paras, lore)
    pts = cut_points(attributed)
    print("log: %s  (%d paragraphs, %d candidate cut points)" % (os.path.basename(log), len(paras), len(pts)))
    if args.list or not pts:
        for i, prior in pts:
            print("  cut %d  (prior speakers: %s)" % (i, ", ".join(prior)))
        return 0

    cut = args.cut if args.cut is not None else pts[len(pts) // 2][0]
    doc = ConfigStore(os.path.join(_ROOT, "data", "cricket-config.sqlite3")).active()
    if not doc:
        print("no active profile in the config DB")
        return 1
    doc = doc[1]
    from cricket.persona.inference import OllamaInferenceClient
    from cricket.persona.llm import LlmPersona
    persona = LlmPersona(OllamaInferenceClient(model=doc["inference"]["model"]), lambda: doc,
                         lore=lore, wiki=WikiIndex(os.path.join(_ROOT, "wiki-cache")),
                         vector=VectorIndex(os.path.join(_ROOT, "wiki-cache")))

    print("\n=== SCENE (lead-up to paragraph %d) ===" % cut)
    for spk, text in attributed[max(0, cut - args.window):cut]:
        print("  [%s] %s" % (spk, text[:200]))

    bot = asyncio.run(replay(persona, attributed, cut))
    print("\n=== do-not-puppet set built from the scene ===")
    print(" ", ", ".join(sorted(bot.scene_owners.get(ROOM, set()))) or "(none)")
    print("=== running ledger ===")
    for line in bot.scene_ledger.get(ROOM, []):
        print("  -", line[:200])
    print("\n=== Cricket's GENERATED next pose ===")
    posed = [c for c in bot.actions.calls if c[0] in ("pose", "emit", "say")]
    gate = [c for c in bot.actions.calls if c[0] == "say_channel"]
    if gate:
        print("  [CONSENT GATE FIRED] %s" % gate[0][2])
    print("  " + (posed[-1][1] if posed else "(no pose -- blocked or silent)"))
    print("\n=== What Cricket ACTUALLY did (reference) ===")
    print("  " + attributed[cut][1][:500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
