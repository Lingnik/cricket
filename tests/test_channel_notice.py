"""The router ignores connect/disconnect and channel join/leave announcements."""

from cricket.router import _CHANNEL_NOTICE


def test_notice_patterns_match():
    for s in [
        "has connected.",
        "has reconnected.",
        "has disconnected.",
        "has joined this channel.",
        "has left this channel.",
    ]:
        assert _CHANNEL_NOTICE.match(s), s


def test_real_chat_not_matched():
    for s in [
        "has a brilliant scheme",
        "says, \"hello\"",
        "waves a pincer-arm dismissively",
        "finally arrived at greatness",
    ]:
        assert not _CHANNEL_NOTICE.match(s), s
