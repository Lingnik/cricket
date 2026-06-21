"""Outbound actions: high-level verbs that format and rate-limit what the bot sends.

A `sender` callable writes one raw line to the MUSH (e.g. Connection.send). Callers use
say_channel/pose_room/emit_room/say_room/page/raw and never format comsys syntax
themselves. Per-location token buckets throttle output; when a bucket is empty the line
is dropped and reported by the return value.
"""

from __future__ import annotations

import time
from typing import Callable, Union

from ..config import parse_rate_limit


class TokenBucket:
    """Simple token bucket. `clock` is injectable for deterministic tests."""

    def __init__(self, count: int, per_seconds: float, clock: Callable = time.monotonic):
        self.capacity = float(count)
        self.per_seconds = float(per_seconds)
        self._clock = clock
        self._tokens = float(count)
        self._last = clock()

    def allow(self) -> bool:
        now = self._clock()
        elapsed = now - self._last
        self._last = now
        if self.per_seconds > 0:
            self._tokens = min(
                self.capacity, self._tokens + elapsed * (self.capacity / self.per_seconds)
            )
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


class Actions:
    def __init__(
        self,
        sender: Callable,
        rate_limits: Union[dict, None] = None,
        clock: Callable = time.monotonic,
    ) -> None:
        # sender: (raw_line: str) -> None
        self._send = sender
        self._clock = clock
        self._buckets: dict = {}
        for location, spec in (rate_limits or {}).items():
            parsed = parse_rate_limit(spec)
            if parsed is not None:
                count, per = parsed
                self._buckets[location] = TokenBucket(count, per, clock)

    def _throttle(self, location: Union[str, None]) -> bool:
        """Return True if allowed to send for this location."""
        if location is None:
            return True
        bucket = self._buckets.get(location)
        if bucket is None:
            return True
        return bucket.allow()

    def say_channel(self, channel: str, text: str) -> bool:
        if not self._throttle(channel):
            return False
        self._send("@chat %s=%s" % (channel, text))
        return True

    def pose_channel(self, channel: str, text: str) -> bool:
        if not self._throttle(channel):
            return False
        self._send("@chat %s=:%s" % (channel, text))
        return True

    def say_room(self, text: str) -> bool:
        self._send('say %s' % text)
        return True

    def pose_room(self, text: str) -> bool:
        self._send(":%s" % text)
        return True

    def emit_room(self, text: str) -> bool:
        self._send("@emit %s" % text)
        return True

    def page(self, target: str, text: str) -> bool:
        self._send("page %s=%s" % (target, text))
        return True

    def raw(self, command: str) -> bool:
        self._send(command)
        return True
