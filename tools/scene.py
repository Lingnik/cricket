"""Tiny multi-turn scene driver over the session harness (127.0.0.1:4300) + control socket (4250).

  python tools/scene.py connect Jessalyn jessalynpass
  python tools/scene.py send Jessalyn "@emit ..."
  python tools/scene.py recv Jessalyn          # drain what this puppet has heard
  python tools/scene.py pose                    # force Cricket to take a turn (!pose via 4250)
  python tools/scene.py rp on|off               # toggle RP on the room (#0)
  python tools/scene.py close                   # quit all puppets, clear the registry

Name->session id is persisted in data/_scene_reg.json so calls compose across shell invocations.
"""

import json
import os
import socket
import sys
import urllib.request

H = "http://127.0.0.1:4300"
REG = os.path.join(os.path.dirname(__file__), "..", "data", "_scene_reg.json")


def _load():
    try:
        return json.load(open(REG))
    except Exception:
        return {}


def _save(d):
    json.dump(d, open(REG, "w"))


def _api(method, path, body=None):
    req = urllib.request.Request(
        H + path, data=(json.dumps(body).encode() if body else None),
        headers={"Content-Type": "application/json"}, method=method)
    return json.loads(urllib.request.urlopen(req, timeout=20).read() or "{}")


def _control(cmd, args=None):
    s = socket.create_connection(("127.0.0.1", 4250), timeout=30)
    try:
        s.sendall((json.dumps({"cmd": cmd, "args": args or []}) + "\n").encode())
        s.settimeout(40)
        buf = b""
        while not buf.endswith(b"\n"):
            x = s.recv(4096)
            if not x:
                break
            buf += x
        return json.loads(buf.decode()) if buf else {}
    finally:
        s.close()


def main():
    cmd = sys.argv[1]
    if cmd == "connect":
        name, pw = sys.argv[2], sys.argv[3]
        sid = _api("POST", "/sessions", {"name": name, "password": pw})["id"]
        reg = _load(); reg[name] = sid; _save(reg)
        print("connected %s -> %s" % (name, sid))
    elif cmd == "send":
        name, line = sys.argv[2], sys.argv[3]
        _api("POST", "/sessions/%s/send" % _load()[name], {"line": line})
        print("[%s] %s" % (name, line))
    elif cmd == "recv":
        name = sys.argv[2]
        r = _api("GET", "/sessions/%s/recv" % _load()[name])
        for ln in r.get("lines", []):
            print("  " + ln)
    elif cmd == "pose":
        print(_control("!pose"))
    elif cmd == "rp":
        on = sys.argv[2] == "on"
        _api("POST", "/api/rp", None)  # placeholder; rp toggled via http below
    elif cmd == "close":
        reg = _load()
        for n, sid in reg.items():
            try:
                _api("DELETE", "/sessions/%s" % sid)
            except Exception:
                pass
        _save({})
        print("closed all (%d)" % len(reg))
    else:
        print("unknown:", cmd)


if __name__ == "__main__":
    main()
