"""Command-line entry points.

    python -m cricket run [--config PATH] [--env PATH]   # start the daemon
    python -m cricket ctl [--host H] [--port P]          # attach the control REPL

Console script names: `cricket` (-> main) and `cricket-ctl` (-> ctl_main).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys
from pathlib import Path

from . import ctl
from .config import load_config, parse_env_file
from .daemon import run_async

DEFAULT_CONFIG = "config.toml"
DEFAULT_ENV = ".env"


def _control_port_free(host: str, port: int) -> bool:
    """True if we can bind the control port. A second daemon would otherwise connect as
    the same character and double-respond, so we refuse to start when it is in use."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _load(config_path: str, env_path: str):
    env = dict(os.environ)
    if env_path and Path(env_path).exists():
        env.update(parse_env_file(env_path))
    return load_config(config_path, env=env)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cricket")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="start the bot daemon")
    run_p.add_argument("--config", default=DEFAULT_CONFIG)
    run_p.add_argument("--env", default=DEFAULT_ENV)
    run_p.add_argument(
        "--persona",
        choices=["stub", "llm"],
        default="stub",
        help="stub = no model (default); llm = local Ollama backend",
    )
    run_p.add_argument("--verbose", "-v", action="store_true",
                       help="stream every activity event (messages in/out, generations, "
                            "distillations) to stdout")

    ctl_p = sub.add_parser("ctl", help="attach the control REPL (with optional live activity tail)")
    ctl_p.add_argument("--host", default="127.0.0.1")
    ctl_p.add_argument("--port", type=int, default=4250)
    ctl_p.add_argument("--stream-port", type=int, default=4252)
    ctl_p.add_argument("--tail", action="store_true", help="start with the activity tail on")

    # `supervise` runs the daemon as a restartable child in the foreground (your shell) and
    # exposes an OOB localhost socket to induce a code-reloading restart of the worker.
    sup_p = sub.add_parser(
        "supervise", help="run the daemon as a restartable child + an OOB restart socket")
    sup_p.add_argument("--config", default=DEFAULT_CONFIG)
    sup_p.add_argument("--env", default=DEFAULT_ENV)
    sup_p.add_argument("--persona", choices=["stub", "llm"], default="stub")
    sup_p.add_argument("--verbose", "-v", action="store_true",
                       help="pass --verbose to the worker (stream activity to this console)")
    sup_p.add_argument("--port", type=int, default=4251,
                       help="OOB supervisor socket port (loopback)")

    args = parser.parse_args(argv)

    if args.command == "run":
        config = _load(args.config, args.env)
        if not _control_port_free("127.0.0.1", config.control.port):
            print(
                "cricket: a daemon already appears to be running (control port %d in "
                "use). Stop it first -- two would both connect as the bot and "
                "double-respond." % config.control.port,
                file=sys.stderr,
            )
            return 1
        print("cricket: control socket on 127.0.0.1:%d" % config.control.port)
        print(
            "cricket: control panel on http://%s:%d/"
            % (config.http.host, config.http.port)
        )
        print("cricket: persona=%s" % args.persona)
        code = 0
        try:
            code = asyncio.run(run_async(config, persona=args.persona, verbose=args.verbose))
        except KeyboardInterrupt:
            pass
        # 42 = restart requested (the `restart` control command). A supervising `cricket
        # supervise` respawns on this code; run standalone, it just exits with it.
        return code or 0

    if args.command == "ctl":
        return ctl.repl(args.host, args.port, args.stream_port, args.tail)

    if args.command == "supervise":
        from .supervisor import supervise
        return supervise(args)

    parser.print_help()
    return 1


def ctl_main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cricket-ctl")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4250)
    parser.add_argument("--stream-port", type=int, default=4252)
    parser.add_argument("--tail", action="store_true", help="start with the activity tail on")
    args = parser.parse_args(argv)
    return ctl.repl(args.host, args.port, args.stream_port, args.tail)


if __name__ == "__main__":
    sys.exit(main())
