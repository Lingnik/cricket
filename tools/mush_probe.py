"""Diagnostic: figure out channel join + delivery + the channel line format.

Cricket joins Public, inspects membership, speaks (to see its own echo and the exact
line format), then Bob speaks. Every response is printed.
"""

from __future__ import annotations

import socket
import time

from mush_admin import recv_quiet, send, pw, HOST, PORT


def login(name, password):
    s = socket.create_connection((HOST, PORT), timeout=5)
    recv_quiet(s)
    send(s, "connect %s %s" % (name, password))
    recv_quiet(s)
    return s


def step(s, cmd, idle=0.5):
    send(s, cmd)
    print(">>> [%s] %s" % (s.getsockname()[1], cmd))
    print(recv_quiet(s, idle=idle).strip())
    print("-" * 50)


def main():
    cricket = login("Cricket", pw("CRICKET_TEST_CRICKET_PW"))
    step(cricket, "@channel/on Public")
    step(cricket, "@channel/who Public")
    step(cricket, "@chat Public=echo test from cricket")  # do we see our own line?

    bob = login("Bob", pw("CRICKET_TEST_BOB_PW"))
    step(bob, "@channel/on Public")
    step(bob, "@chat Public=hello from bob")
    step(bob, ":waves at everyone.")        # room pose (PARANOID prefix?)
    time.sleep(0.5)

    print("=== CRICKET inbox after bob spoke ===")
    print(recv_quiet(cricket, idle=0.8, maxwait=4.0).strip())

    for s in (cricket, bob):
        send(s, "QUIT")
        s.close()


if __name__ == "__main__":
    main()
