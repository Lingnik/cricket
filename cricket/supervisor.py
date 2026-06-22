"""Foreground supervisor: run the daemon as a restartable child + an OOB restart socket.

Run this in your shell (`python -m cricket supervise --persona llm`). It launches `cricket run`
as a child subprocess with stdio inherited (the daemon's output streams to your console exactly
as if you ran it directly) and stays in the foreground. A loopback OOB socket lets an agent or
operator induce a CODE-reloading restart of the worker without touching your process:

    echo '{"cmd":"restart"}' | <send to 127.0.0.1:4251>   # respawn with fresh code
    {"cmd":"stop"}      # terminate worker + exit the supervisor
    {"cmd":"status"}    # worker pid / alive / restart count

A restart works two ways: this socket force-terminates the worker (handles a hung daemon), and
the daemon's own `restart` control command exits with code 42 (a clean self-requested restart);
either way the supervisor respawns. Self-exec is avoided deliberately -- on Windows it would
detach from the interactive terminal.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time

RESTART_CODE = 42  # the daemon's `restart` command exits with this; the supervisor respawns.


class Supervisor:
    def __init__(self, child_argv, sock_host: str = "127.0.0.1", sock_port: int = 4251):
        self.child_argv = list(child_argv)
        self.sock_host = sock_host
        self.sock_port = sock_port
        self._lock = threading.Lock()
        self._child = None
        self._stop = False
        self._restart = False
        self._restarts = 0

    # -- child lifecycle -------------------------------------------------------
    def _spawn(self):
        with self._lock:
            self._restart = False
            self._child = subprocess.Popen(self.child_argv)  # stdio inherited
        return self._child

    def _terminate_child(self, grace: float = 6.0) -> None:
        """Ask the child to stop, escalating to a hard kill if it does not. Polls rather than
        wait()s so it never races the main loop's wait() on the same process."""
        with self._lock:
            child = self._child
        if child is None or child.poll() is not None:
            return
        try:
            child.terminate()
        except OSError:
            pass
        deadline = time.time() + grace
        while time.time() < deadline:
            if child.poll() is not None:
                return
            time.sleep(0.1)
        try:
            child.kill()
        except OSError:
            pass

    # -- OOB control socket ----------------------------------------------------
    def _handle_cmd(self, cmd: str) -> dict:
        if cmd == "restart":
            with self._lock:
                self._restart = True
            self._terminate_child()
            return {"ok": True, "text": "restarting worker"}
        if cmd == "stop":
            with self._lock:
                self._stop = True
            self._terminate_child()
            return {"ok": True, "text": "stopping supervisor + worker"}
        if cmd == "status":
            with self._lock:
                child = self._child
            alive = child is not None and child.poll() is None
            return {"ok": True, "pid": (child.pid if child else None),
                    "alive": alive, "restarts": self._restarts}
        return {"ok": False, "text": "unknown cmd: %s" % cmd}

    def _serve_socket(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind((self.sock_host, self.sock_port))
        except OSError as exc:
            print("cricket supervise: cannot bind OOB socket %s:%d (%s)"
                  % (self.sock_host, self.sock_port, exc), file=sys.stderr, flush=True)
            return
        srv.listen(5)
        srv.settimeout(0.5)
        while not self._stop:
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                try:
                    req = json.loads(conn.recv(8192).decode("utf-8") or "{}")
                    resp = self._handle_cmd((req.get("cmd") or "").strip())
                except (ValueError, OSError, UnicodeDecodeError):
                    resp = {"ok": False, "text": "bad request"}
                try:
                    conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                except OSError:
                    pass
        srv.close()

    # -- main loop -------------------------------------------------------------
    def run(self) -> int:
        threading.Thread(target=self._serve_socket, daemon=True).start()
        print("cricket supervise: OOB restart socket on %s:%d (cmds: restart|stop|status)"
              % (self.sock_host, self.sock_port), flush=True)
        backoff = 1.0
        while not self._stop:
            child = self._spawn()
            code = child.wait()
            with self._lock:
                restart_req, stop_req = self._restart, self._stop
            if stop_req:
                break
            if restart_req or code == RESTART_CODE:
                self._restarts += 1
                print("cricket supervise: restarting worker (#%d, exit=%s) with fresh code"
                      % (self._restarts, code), flush=True)
                backoff = 1.0
                time.sleep(0.4)  # let the worker's ports (4250/4280) release before respawning
                continue
            if code == 0:
                print("cricket supervise: worker exited cleanly (0); stopping.", flush=True)
                break
            # Unexpected exit (crash): respawn with backoff.
            self._restarts += 1
            print("cricket supervise: worker exited %s; respawning in %.0fs."
                  % (code, backoff), flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
        self._terminate_child()
        return 0


def supervise(args) -> int:
    child_argv = [sys.executable, "-m", "cricket", "run",
                  "--persona", args.persona, "--config", args.config, "--env", args.env]
    sup = Supervisor(child_argv, sock_port=args.port)
    try:
        return sup.run()
    except KeyboardInterrupt:
        with sup._lock:
            sup._stop = True
        sup._terminate_child()
        print("\ncricket supervise: stopped.", flush=True)
        return 0
