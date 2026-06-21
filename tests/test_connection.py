"""Connection outbound queue + drain behavior (no real socket)."""

import asyncio

from cricket.mush.connection import Connection


class FakeWriter:
    """Records writes and drain() calls in order."""

    def __init__(self):
        self.writes = []
        self.drains = 0

    def write(self, data):
        self.writes.append(data)

    async def drain(self):
        self.drains += 1


def _conn():
    return Connection("host", 4201, "Cricket", "pw", on_line=lambda line: None)


def test_send_before_connect_does_not_crash():
    c = _conn()
    assert c._outq is None  # no connection yet
    c.send("hello")  # must not raise -- dropped silently


def test_send_collapses_newlines_to_one_wire_line():
    async def go():
        c = _conn()
        c._outq = asyncio.Queue()
        c.send("first\nsecond\r\nthird")
        return c._outq.get_nowait()

    data = asyncio.run(go())
    assert data.endswith(b"\r\n")
    body = data[:-2]
    # exactly one command on the wire: no embedded CR/LF that would split it server-side
    assert b"\n" not in body and b"\r" not in body
    assert b"first" in body and b"second" in body and b"third" in body


def test_write_loop_drains_each_message_in_order():
    async def go():
        c = _conn()
        c._outq = asyncio.Queue()
        w = FakeWriter()
        task = asyncio.ensure_future(c._write_loop(w))
        c.send("a")
        c.send("b")
        c.send("c")
        await asyncio.sleep(0.05)  # let the writer task drain the queue
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return w

    w = asyncio.run(go())
    assert w.writes == [b"a\r\n", b"b\r\n", b"c\r\n"]
    assert w.drains == 3  # flushed after every write, not buffered


def test_teardown_drops_further_sends():
    async def go():
        c = _conn()
        c._outq = asyncio.Queue()
        c._writer_task = asyncio.ensure_future(c._write_loop(FakeWriter()))
        c._teardown_writer()
        assert c._outq is None
        assert c._writer_task is None
        c.send("x")  # dropped, no crash
        await asyncio.sleep(0)

    asyncio.run(go())


def test_tls_insecure_is_opt_in_only():
    secure = _conn()
    assert secure.tls_insecure is False
    relaxed = Connection(
        "h", 4202, "Cricket", "pw", on_line=lambda line: None, tls_insecure=True
    )
    assert relaxed.tls_insecure is True
