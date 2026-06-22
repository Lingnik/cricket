"""Activity event bus: one publish point for everything the daemon does -- messages in/out of
the MUSH, LLM generations (with their retrieval: dossiers, wiki topics, vector hits), and
distillations -- fanned out to live sinks (the `--verbose` stdout printer and the `ctl` tail
stream). Subscribers are plain callables(evt); publish is best-effort and never raises into the
caller, so a slow or broken viewer can never disrupt the bot.
"""

from __future__ import annotations

import threading
import time


class ActivityBus:
    def __init__(self) -> None:
        self._subs: list = []
        self._lock = threading.Lock()

    def subscribe(self, cb):
        """Register a callable(evt). Returns an unsubscribe callable."""
        with self._lock:
            self._subs.append(cb)

        def cancel():
            with self._lock:
                if cb in self._subs:
                    self._subs.remove(cb)

        return cancel

    def publish(self, kind: str, **data) -> None:
        self.publish_event({"kind": kind, **data})

    def publish_event(self, evt: dict) -> None:
        evt.setdefault("ts", round(time.time(), 3))
        with self._lock:
            subs = list(self._subs)
        for cb in subs:
            try:
                cb(evt)
            except Exception:  # a viewer must never break the bot
                pass


def format_event(evt: dict) -> str:
    """Render one activity event as a single human-readable line (verbose stdout + ctl tail),
    prefixed with its epoch timestamp."""
    k = evt.get("kind", "?")
    if k == "mush.in":
        body = "[in ] %s(%s) %s: %s" % (
            evt.get("speaker") or "?", evt.get("dbref") or "?",
            evt.get("speech") or "", (evt.get("text") or "")[:160])
    elif k == "mush.out":
        body = "[out] %s" % (evt.get("line") or "")[:200]
    elif k == "generate":
        ret = []
        if evt.get("dossiers_injected"):
            ret.append("dossiers=%s" % evt["dossiers_injected"])
        if evt.get("wiki_topics"):
            ret.append("wiki=%s" % evt["wiki_topics"])
        if evt.get("vector_hit"):
            ret.append("vector=%s" % evt["vector_hit"])
        if evt.get("thinking_enabled"):
            ret.append("reasoned")
        body = "[gen] %s %s %s -> %r" % (
            evt.get("mode") or "?", evt.get("room") or "?",
            " ".join(ret), (evt.get("clean_output") or "")[:120])
    elif k == "distill":
        body = "[dst] +%r actors=%s" % ((evt.get("ledger_entry") or "")[:90], evt.get("actors"))
    elif k == "cmd":
        body = "[cmd] %s %s" % (evt.get("name"), " ".join(evt.get("args") or []))
    else:
        extra = {key: v for key, v in evt.items() if key not in ("kind", "ts")}
        body = "[%s] %s" % (k, extra)
    ts = evt.get("ts")
    return ("%.3f %s" % (ts, body)) if ts is not None else body
