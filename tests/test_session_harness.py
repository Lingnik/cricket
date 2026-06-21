"""Line-buffering logic for the MUSH session harness (tools/mush_session_server.py)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from mush_session_server import _split_lines  # noqa: E402


def test_split_lines_basic():
    lines, rem = _split_lines("", b"hello\r\nworld\r\n")
    assert lines == ["hello", "world"]
    assert rem == ""


def test_split_lines_drops_blank_formatting_lines():
    lines, _ = _split_lines("", b"a\r\n\r\n  \r\nb\r\n")
    assert lines == ["a", "b"]


def test_split_lines_carries_partial_across_chunks():
    lines, rem = _split_lines("", b"par")
    assert lines == [] and rem == "par"
    lines2, rem2 = _split_lines(rem, b"tial\r\n")
    assert lines2 == ["partial"] and rem2 == ""


def test_split_lines_strips_telnet_iac():
    # IAC WILL ECHO (0xFF 0xFB 0x01) prefix is stripped before the text.
    lines, _ = _split_lines("", b"\xff\xfb\x01ok\r\n")
    assert lines == ["ok"]
