"""cricket-ctl: a thin REPL over the daemon's control socket.

Each input line is sent as one command; the daemon's reply is printed. Type `quit` or
`exit` (or send EOF) to leave.
"""

from __future__ import annotations

import asyncio
import json


async def _send_one(host: str, port: int, name: str, args: list) -> dict:
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write((json.dumps({"cmd": name, "args": args}) + "\n").encode("utf-8"))
        await writer.drain()
        line = await reader.readline()
        if not line:
            return {"ok": False, "text": "no response"}
        return json.loads(line.decode("utf-8"))
    finally:
        writer.close()


def repl(host: str = "127.0.0.1", port: int = 4250) -> int:
    print("cricket-ctl -> %s:%d  (quit to exit)" % (host, port))
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
        name, args = parts[0], parts[1:]
        try:
            resp = asyncio.run(_send_one(host, port, name, args))
        except OSError as exc:
            print("connection error: %s" % exc)
            continue
        if resp.get("text"):
            print(resp["text"])
        if not resp.get("ok"):
            print("(command reported failure)")
    return 0
