"""Tiny MUSH socket driver for setting up / inspecting the local test PennMUSH.

Not part of the bot runtime -- a dev/test harness. Connects over plain TCP, strips
telnet IAC negotiation, sends commands line by line, and prints each response.

Usage:
    python tools/mush_admin.py login <name> <password> [cmd ...]   # run cmds, print replies
    python tools/mush_admin.py setup                               # bootstrap the test world
"""

from __future__ import annotations

import os
import socket
import sys
import time

HOST = os.environ.get("CRICKET_MUSH_HOST", "100.88.188.43")
PORT = int(os.environ.get("CRICKET_MUSH_PORT", "4201"))


def pw(var: str) -> str:
    """Read a test-account password from the environment. No credentials live in this
    file (it is committed to a public repo); set the CRICKET_TEST_*_PW vars in the
    gitignored .env -- see .env.example."""
    val = os.environ.get(var)
    if not val:
        sys.exit("error: %s is not set (put test creds in .env -- see .env.example)" % var)
    return val


def strip_iac(data: bytes) -> bytes:
    """Remove telnet IAC sequences so the text parses cleanly."""
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b == 0xFF:  # IAC
            if i + 1 >= n:
                break
            cmd = data[i + 1]
            if cmd in (0xFB, 0xFC, 0xFD, 0xFE):  # WILL/WONT/DO/DONT <opt>
                i += 3
                continue
            if cmd == 0xFA:  # SB ... IAC SE
                j = data.find(b"\xff\xf0", i)
                if j == -1:
                    break
                i = j + 2
                continue
            i += 2
            continue
        out.append(b)
        i += 1
    return bytes(out)


def recv_quiet(s: socket.socket, idle: float = 0.6, maxwait: float = 6.0) -> str:
    """Read until the server goes quiet for `idle` seconds (or `maxwait` elapses)."""
    s.setblocking(False)
    buf = bytearray()
    start = time.time()
    last = time.time()
    while time.time() - start < maxwait:
        try:
            chunk = s.recv(4096)
            if chunk:
                buf += chunk
                last = time.time()
            else:
                break
        except (BlockingIOError, InterruptedError):
            if buf and (time.time() - last > idle):
                break
            time.sleep(0.05)
    return strip_iac(bytes(buf)).decode("latin-1", "replace")


def send(s: socket.socket, line: str) -> None:
    s.sendall((line + "\r\n").encode("latin-1"))


def run(name: str, password: str, commands: list) -> None:
    s = socket.create_connection((HOST, PORT), timeout=5)
    recv_quiet(s)  # connect screen
    send(s, "connect %s %s" % (name, password))
    print(">>> connect %s" % name)
    print(recv_quiet(s).strip())
    for c in commands:
        send(s, c)
        print(">>> " + c)
        print(recv_quiet(s).strip())
        print("-" * 50)
    send(s, "QUIT")
    s.close()


def setup_commands() -> list:
    """The test-world bootstrap. Account passwords come from the CRICKET_TEST_*_PW
    environment variables (set in .env), so no credentials are hardcoded here."""
    return [
        # Secure God (currently passwordless).
        "@password =%s" % pw("CRICKET_TEST_GOD_PW"),
        # Create the bot and two test players.
        "@pcreate Cricket=%s" % pw("CRICKET_TEST_CRICKET_PW"),
        "@pcreate Bazil=%s" % pw("CRICKET_TEST_BAZIL_PW"),
        "@pcreate Bob=%s" % pw("CRICKET_TEST_BOB_PW"),
        # Bazil is an admin/wizard for testing privileged commands.
        "@set *Bazil=WIZARD",
        # The bot sees real sources on spoofable output.
        "@set *Cricket=NOSPOOF",
        "@set *Cricket=PARANOID",
        # Channels: a PG public, an anything-goes lounge, and an OOC control channel.
        "@channel/add Public",
        "@channel/add Lounge",
        "@channel/add OOC",
        # Global 'ooc <msg>' / 'ooc :<emote>' command so admins can talk on OOC and
        # command the bot (addcom is disabled). Set all flags BEFORE the @tel -- once it
        # is in the Master Room the object can no longer be matched by name.
        "@create OOC Relay",
        "@set OOC Relay=WIZARD",
        "@set OOC Relay=!NO_COMMAND",
        "&CMD.OOC OOC Relay=$ooc *:@force %#=@chat OOC=%0",
        "@tel OOC Relay=#2",
        # Report dbrefs so we can fill the bot allowlist / identity.
        "think DBREF Cricket=[num(*Cricket)]",
        "think DBREF Bazil=[num(*Bazil)]",
        "think DBREF Bob=[num(*Bob)]",
        "@channel/what",
    ]


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "setup":
        # On a fresh world God ("One") is passwordless and accepts any password; after
        # setup it has CRICKET_TEST_GOD_PW. Connect with that value either way.
        run("One", pw("CRICKET_TEST_GOD_PW"), setup_commands())
    elif len(sys.argv) >= 4 and sys.argv[1] == "login":
        run(sys.argv[2], sys.argv[3], sys.argv[4:])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
