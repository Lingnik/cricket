"""Turn tracing -- the production debug log for Cricket's generations.

Every generated turn writes one structured JSON line capturing WHAT actually happened inside the
persona: which characters' dossiers were injected, whether the hidden reasoning step ran (and its
plan), shared-history / wiki / vector hits, the do-not-puppet set, the prompt size, and the raw vs
cleaned output. The per-turn distillation writes a second line (the ledger update + extracted
actors). The result is an append-only JSONL artifact that survives the session and is analyzable
after the fact (jq/grep) -- so "did context inject? did reasoning run? did summarization fire?" is
answerable from a log, exactly as it must be in production.

Traces are DEBUG LOGS, not memory: nothing here is fed back into Cricket, so they never pollute
interaction memory and can be kept or discarded freely.
"""

from __future__ import annotations

import json
import os
import threading
import time


class TurnTracer:
    """Append-only JSONL sink. Thread-safe (the HTTP thread, the loop, and command handlers may
    all emit). One line per record; `kind` distinguishes 'generate' from 'distill'."""

    def __init__(self, path: str, on_emit=None) -> None:
        self.path = path
        # Optional second sink (e.g. the activity bus) called with each record, so live viewers
        # see generations/distillations as they happen -- in addition to the durable JSONL.
        self.on_emit = on_emit
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._lock = threading.Lock()

    def emit(self, record: dict) -> None:
        rec = dict(record)
        rec.setdefault("ts", round(time.time(), 3))
        line = json.dumps(rec, ensure_ascii=True, default=str)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        if self.on_emit is not None:
            try:
                # Keep the live bus event (verbose stdout + ctl tail) lean: the full prompt(s) are
                # large and live in the JSONL for the `prompt` command to fetch on demand.
                slim = {k: v for k, v in rec.items() if k not in ("prompt", "plan_prompt")}
                self.on_emit(slim)
            except Exception:
                pass


class NullTracer:
    """No-op tracer (used by evals / tests where no trace artifact is wanted)."""

    def emit(self, record: dict) -> None:  # noqa: D401
        pass
