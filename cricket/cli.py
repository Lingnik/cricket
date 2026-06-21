"""Command-line entry points.

    python -m cricket run [--config PATH] [--env PATH]   # start the daemon
    python -m cricket ctl [--host H] [--port P]          # attach the control REPL

Console script names: `cricket` (-> main) and `cricket-ctl` (-> ctl_main).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from . import ctl
from .config import load_config, parse_env_file
from .daemon import run_async

DEFAULT_CONFIG = "config.toml"
DEFAULT_ENV = ".env"


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

    ctl_p = sub.add_parser("ctl", help="attach the control REPL")
    ctl_p.add_argument("--host", default="127.0.0.1")
    ctl_p.add_argument("--port", type=int, default=4250)

    args = parser.parse_args(argv)

    if args.command == "run":
        config = _load(args.config, args.env)
        try:
            asyncio.run(run_async(config))
        except KeyboardInterrupt:
            pass
        return 0

    if args.command == "ctl":
        return ctl.repl(args.host, args.port)

    parser.print_help()
    return 1


def ctl_main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cricket-ctl")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4250)
    args = parser.parse_args(argv)
    return ctl.repl(args.host, args.port)


if __name__ == "__main__":
    sys.exit(main())
