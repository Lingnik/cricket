"""Activity bus + event formatter + the tracer's bus hook."""

from cricket.activity import ActivityBus, format_event


def _boom(_evt):
    raise RuntimeError("subscriber blew up")


def test_bus_publishes_to_subscribers_and_unsubscribes():
    bus = ActivityBus()
    got = []
    cancel = bus.subscribe(got.append)
    bus.publish("mush.in", speaker="Bob", dbref="#5", speech="say", text="hi")
    assert len(got) == 1 and got[0]["kind"] == "mush.in" and got[0]["text"] == "hi"
    assert "ts" in got[0]
    cancel()
    bus.publish("mush.out", line="x")
    assert len(got) == 1  # no longer subscribed


def test_bus_isolates_a_broken_subscriber():
    bus = ActivityBus()
    ok = []
    bus.subscribe(_boom)        # raises every time
    bus.subscribe(ok.append)
    bus.publish("x")            # must not raise; the healthy subscriber still fires
    assert len(ok) == 1


def test_format_event_renders_each_kind():
    assert format_event(
        {"kind": "mush.in", "speaker": "Bob", "dbref": "#5", "speech": "emit", "text": "waves"}
    ).startswith("[in ]")
    assert "@chat" in format_event({"kind": "mush.out", "line": "@chat Pub=hi"})
    g = format_event({"kind": "generate", "mode": "rp", "room": "#0",
                      "dossiers_injected": ["Johanna"], "vector_hit": "Jasmine",
                      "thinking_enabled": True, "clean_output": "Cricket poses."})
    assert g.startswith("[gen]") and "dossiers" in g and "vector" in g and "reasoned" in g
    assert format_event({"kind": "distill", "ledger_entry": "a note", "actors": ["Bob"]}).startswith("[dst]")


def test_tracer_on_emit_hook_fires(tmp_path):
    from cricket.trace import TurnTracer
    got = []
    t = TurnTracer(str(tmp_path / "t.jsonl"), on_emit=got.append)
    t.emit({"kind": "generate", "room": "#0"})
    assert got and got[0]["kind"] == "generate" and got[0]["room"] == "#0"
