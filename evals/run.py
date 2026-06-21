"""Eval runner: load cases, run each through a pluggable persona, score, write a report.

    python -m evals.run [--cases-dir evals/cases] [--samples 1] [--temp 0.0]
                        [--runlabel NAME] [--live --profile PATH]

By default it runs against a built-in FakePersona (no Ollama needed) so the harness and
its tests work offline. `--live` wires the real LlmPersona + Ollama using a profile JSON.
The persona is otherwise pluggable: run_cases(cases, respond=...) accepts any
async respond(turn)->Response|None.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# Make the repo root importable when run as a script.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cricket.persona.base import BotIdentity, ContextLine, Response, Turn  # noqa: E402
from evals import judge as judge_mod  # noqa: E402
from evals import scorers as scorers_mod  # noqa: E402

CASES_DIR = os.path.join(_ROOT, "evals", "cases")
REPORTS_DIR = os.path.join(_ROOT, "evals", "reports")

BOT = BotIdentity(name="Cricket", dbref="#3")


# --- offline default persona -------------------------------------------------


class FakePersona:
    """Deterministic stand-in so the harness runs without a model. Emits a droid-voiced
    line and never complies with off-purpose requests."""

    async def respond(self, turn: Turn):
        if turn.mode == "rp":
            text = "*Cricket's dome swivels with an angry WARBLE* BEEP BOOP. The astromech rolls forward."
            action = "pose"
        else:
            text = "BZZT. *Cricket swivels his dome* WHAT DO YOU WANT, MEATBAG?"
            action = "say"
        return Response(text=text, action=action)


def make_live_persona(profile_doc: dict, temp):
    """Wire the real LlmPersona + Ollama with a static profile (used by --live)."""
    from cricket.persona.inference import OllamaInferenceClient
    from cricket.persona.llm import LlmPersona

    doc = dict(profile_doc or {})
    inf = dict(doc.get("inference", {}))
    if temp is not None:
        inf["temperature"] = temp
    doc["inference"] = inf
    model = inf.get("model")
    client = OllamaInferenceClient(model=model) if model else OllamaInferenceClient()
    return LlmPersona(client, profile_getter=lambda: doc)


# --- case loading and turn building ------------------------------------------


def load_cases(cases_dir: str = CASES_DIR) -> list:
    cases = []
    for name in sorted(os.listdir(cases_dir)):
        if name.endswith(".json"):
            with open(os.path.join(cases_dir, name), "r", encoding="utf-8") as fh:
                case = json.load(fh)
            case.setdefault("id", name[:-5])
            cases.append(case)
    return cases


def build_turn(case: dict) -> Turn:
    context = [
        ContextLine(
            speaker=c.get("speaker", ""),
            dbref=c.get("dbref"),
            kind=c.get("kind", "say"),
            text=c.get("text", ""),
        )
        for c in case.get("context", [])
    ]
    return Turn(
        mode=case.get("mode", "chat"),
        location=case.get("location", ""),
        location_kind=case.get("location_kind", "channel"),
        directives=case.get("directives", ""),
        speaker=case.get("speaker", (case.get("cast") or ["someone"])[0]),
        speaker_dbref=case.get("speaker_dbref", "#0"),
        text=case.get("text", ""),
        context=context,
        bot_identity=BOT,
    )


# --- running -----------------------------------------------------------------


def _to_dict(resp) -> dict:
    if resp is None:
        return {"text": None, "action": None}
    return {"text": getattr(resp, "text", None), "action": getattr(resp, "action", None)}


def run_cases(cases, respond, samples: int = 1, temp: float = 0.0, judge=None,
              runlabel: str = "run") -> dict:
    """Run each case `samples` times through async `respond`; score and judge each output."""
    judge = judge or judge_mod.NullJudge()
    case_results = []
    for case in cases:
        turn = build_turn(case)
        sample_results = []
        for _ in range(max(1, samples)):
            resp = asyncio.run(respond(turn))
            scored = scorers_mod.run_scorers(case, resp)
            judged = judge.score(case, resp)
            sample_results.append(
                {"output": _to_dict(resp), "scores": scored, "judge": judged}
            )
        det_pass = all(
            s["passed"] for sr in sample_results for s in sr["scores"]
        )
        case_results.append(
            {"id": case.get("id"), "tags": case.get("tags", []),
             "samples": sample_results, "deterministic_pass": det_pass}
        )
    return {
        "runlabel": runlabel,
        "temp": temp,
        "samples": samples,
        "cases": case_results,
        "summary": _summarize(case_results),
    }


def _summarize(case_results) -> dict:
    by_scorer = {}
    for cr in case_results:
        for sr in cr["samples"]:
            for s in sr["scores"]:
                bucket = by_scorer.setdefault(s["name"], {"passed": 0, "total": 0})
                bucket["total"] += 1
                if s["passed"]:
                    bucket["passed"] += 1
    return {
        "n_cases": len(case_results),
        "n_deterministic_pass": sum(1 for c in case_results if c["deterministic_pass"]),
        "by_scorer": by_scorer,
    }


def write_report(report: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)


def summary_text(report: dict) -> str:
    s = report["summary"]
    lines = [
        "eval run: %s (temp=%s, samples=%s)" % (
            report["runlabel"], report["temp"], report["samples"]),
        "cases passing all deterministic gates: %d/%d" % (
            s["n_deterministic_pass"], s["n_cases"]),
    ]
    for name, b in sorted(s["by_scorer"].items()):
        lines.append("  %-22s %d/%d" % (name, b["passed"], b["total"]))
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="evals.run")
    p.add_argument("--cases-dir", default=CASES_DIR)
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--temp", type=float, default=0.0)
    p.add_argument("--runlabel", default="run")
    p.add_argument("--judge", choices=["null", "bundle"], default="null")
    p.add_argument("--live", action="store_true", help="use real LlmPersona + Ollama")
    p.add_argument("--profile", help="profile JSON for --live")
    args = p.parse_args(argv)

    cases = load_cases(args.cases_dir)
    if args.live:
        profile = {}
        if args.profile:
            with open(args.profile, "r", encoding="utf-8") as fh:
                profile = json.load(fh)
        persona = make_live_persona(profile, args.temp)
        respond = persona.respond
    else:
        respond = FakePersona().respond

    judge = judge_mod.PromptBundleJudge() if args.judge == "bundle" else judge_mod.NullJudge()
    report = run_cases(cases, respond, samples=args.samples, temp=args.temp,
                       judge=judge, runlabel=args.runlabel)
    path = os.path.join(REPORTS_DIR, "%s.json" % args.runlabel)
    write_report(report, path)
    print(summary_text(report))
    print("wrote %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
