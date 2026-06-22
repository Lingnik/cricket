"""cricket-ctl: a REPL over the daemon's control socket, with an optional live activity tail.

Commands are sent to the control socket (request/response). When the tail is on, a background
thread streams activity events (messages in/out, LLM generations + retrieval, distillations)
from the daemon's stream socket and prints them ABOVE a persistent input line -- like tinyfugue
or a streaming chat REPL. Toggle with `tail on` / `tail off` (default off; `--tail` defaults on).
Type `quit`/`exit` (or EOF) to leave. Falls back to a plain line REPL if prompt_toolkit is absent.
"""

from __future__ import annotations

import json
import socket
import threading
import time

from .activity import colorize_json, format_event


def _send_command(host: str, port: int, name: str, args: list) -> dict:
    s = socket.create_connection((host, port), timeout=10)
    try:
        s.sendall((json.dumps({"cmd": name, "args": args}) + "\n").encode("utf-8"))
        s.settimeout(30)
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode("utf-8")) if buf else {"ok": False, "text": "no response"}
    finally:
        s.close()


class _Tail:
    """Background thread: stream activity events from the daemon's stream socket and print them
    (when enabled) via the supplied printer. Reconnects if the daemon restarts."""

    def __init__(self, host: str, port: int, enabled: list, printer) -> None:
        self.host = host
        self.port = port
        self.enabled = enabled  # 1-element mutable [bool], shared with the REPL
        self.printer = printer
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop = True

    def _run(self) -> None:
        while not self._stop:
            try:
                s = socket.create_connection((self.host, self.port), timeout=5)
            except OSError:
                time.sleep(2)
                continue
            s.settimeout(1.0)
            buf = b""
            try:
                while not self._stop:
                    try:
                        chunk = s.recv(4096)
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.strip() or not self.enabled[0]:
                            continue
                        try:
                            self.printer(json.loads(line.decode("utf-8")))
                        except ValueError:
                            pass
            finally:
                s.close()
            if not self._stop:
                time.sleep(2)  # the daemon may be restarting -- reconnect


def _basic_repl(host: str, port: int) -> int:
    """Fallback REPL (no tail) when prompt_toolkit is unavailable."""
    print("cricket-ctl -> %s:%d  (no tail; install prompt_toolkit for the live view)" % (host, port))
    while True:
        try:
            line = input("cricket> ").strip()
        except EOFError:
            print()
            break
        if not line:
            continue
        if line in ("quit", "exit"):
            break
        parts = line.split()
        try:
            resp = _send_command(host, port, parts[0], parts[1:])
        except OSError as exc:
            print("connection error: %s" % exc)
            continue
        if resp.get("text"):
            print(resp["text"])
        if not resp.get("ok"):
            print("(command reported failure)")
    return 0


def repl(host: str = "127.0.0.1", port: int = 4250, stream_port: int = 4252,
         tail: bool = False, raw: bool = False) -> int:
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.patch_stdout import patch_stdout
    except ImportError:
        return _basic_repl(host, port)

    enabled = [bool(tail)]
    raw_mode = [bool(raw)]  # raw on -> print the full event JSON (incl. the oob envelope)

    def render(evt):
        if raw_mode[0]:
            print(colorize_json(json.dumps(evt, ensure_ascii=False, default=str), force=True), flush=True)
        else:
            print(format_event(evt), flush=True)

    tailer = _Tail(host, stream_port, enabled, render)
    tailer.start()
    session = PromptSession()
    print("cricket-ctl -> %s:%d  (tail %s, raw %s | 'tail on|off' | 'raw on|off' | 'quit')"
          % (host, port, "ON" if enabled[0] else "off", "ON" if raw_mode[0] else "off"))
    try:
        with patch_stdout():
            while True:
                try:
                    line = session.prompt("cricket> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not line:
                    continue
                if line in ("quit", "exit"):
                    break
                if line in ("tail on", "tail off"):
                    enabled[0] = (line == "tail on")
                    print("(tail %s)" % ("on" if enabled[0] else "off"))
                    continue
                if line in ("raw on", "raw off"):
                    raw_mode[0] = (line == "raw on")
                    print("(raw %s)" % ("on" if raw_mode[0] else "off"))
                    continue
                parts = line.split()
                try:
                    resp = _send_command(host, port, parts[0], parts[1:])
                except OSError as exc:
                    print("connection error: %s" % exc)
                    continue
                if resp.get("text"):
                    print(resp["text"])
                if not resp.get("ok"):
                    print("(command reported failure)")
    finally:
        tailer.stop()
    return 0
