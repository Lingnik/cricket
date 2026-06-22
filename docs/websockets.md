# cricket — WebSocket + `oob()` inbound (happy path)

A more robust inbound transport for world traffic. Instead of regex-parsing rendered
telnet lines (the fragile, spoofable path), the bot connects over **WebSocket** and
receives each heard message as a **structured JSON object** carrying an **engine-derived
speaker dbref** that the originating player cannot forge.

This replaces the inbound half of the `Connection`/`Parser` layers for *world traffic*
(see `DESIGN.md`). Outbound (`say`/`pose`/`@emit`/`page`) still goes over the same socket
as ordinary commands.

> Status: mechanism verified end-to-end against a live PennMUSH (1.8.x) — GMCP and
> WebSocket both deliver the identical JSON. The relay, the framing, and every gotcha
> below were confirmed by running them, not inferred.

---

## Why

The classic problem with reading a MUSH over telnet:

1. **Attribution is in-band, forgeable text.** A line like `[Bob(#5)] ...` (the NOSPOOF/
   PARANOID prefix) is just characters. A player can `@emit ...%r[Wizard(#1)] ...` and
   inject a newline so the second physical line arrives with no prefix — or a fake one.
   The prefix is added **once per message, not per line**, so newline injection defeats it.
2. **Message ≠ line ≠ frame.** Rendered output is split by markup and newlines; one logical
   message can span several lines/frames, and the attribution prefix is a *separate* unit
   from the body. There is no reliable "one unit = one attributed message."

The fix has to be manufactured **on the receiver side, from data the emitter cannot touch**.
PennMUSH's enactor register `%#` is exactly that: the engine sets it to the true speaker.
A receiver-side listener that fires `oob()` keyed on `%#` yields, per heard message:

- **`from`/`dbref` from `%#`** — unforgeable; an attacker's fake `[Wizard(#1)]` text rides
  harmlessly *inside* `msg`.
- **Exactly one JSON object per message** — isolation is structural, not a delimiter you
  hope holds. Control characters (`%r`→newline, `%t`→tab) are JSON-escaped (`\n`, `\t`),
  losslessly, inside one string.

Trust assumptions reduce to: the server itself, and that `%#` is correct (inherent to the
engine). Nothing the sender controls is trusted.

> Not used: `WSJSON()` exists but is **emitter-side** — the sender chooses to format JSON.
> Useless here: the sender is the untrusted party. Ignore it.

---

## Architecture (receiver-side relay)

```
  other player ──@emit──▶ room ──hears──▶ Cricket(@listen)
                                              │  AHEAR fires (speaker = %#, text = %0)
                                              ▼
                                     oob(name(me), <package>, json{from,dbref,msg})
                                              │  out-of-band; bypasses the hear path → no loop
                                              ▼
        ws://host/wsclient ◀── JSON channel ──┘   {"from":"Bob","dbref":"#5","msg":"...","gmcp":"<package>"}
```

- The relay runs in **Cricket's own context**, fired by the engine when Cricket *hears* a
  message. The emitter has no influence over whether/how it runs.
- `oob()` writes GMCP/WebSocket frames **directly** to the descriptor — it does **not** go
  through the in-band notify path, so the relayed copy **cannot re-trigger the listener**.
  No loop, structurally (not via clever speaker≠listener gymnastics).
- Because `AHEAR` fires only when `speaker != listener`, even an `oob()`-induced in-band
  message wouldn't re-fire it — but `oob()` is out-of-band anyway, so it's doubly safe.

---

## Server requirements & how to verify

Run this **as the bot character** on the target server (the `config()` calls are mortal-
readable on most servers; if any returns `#-1`, skip to the end-to-end proof below):

```
think use_ws=[config(use_ws)] ws_url=[config(ws_url)]
think player_listen=[config(player_listen)] player_ahear=[config(player_ahear)]
think side_effects=[config(function_side_effects)]
think OOBTEST=[oob(name(me), Probe.X, json(object, ok, json(string, yes)))]
think terminfo=[terminfo(me)]
```

| Must hold | Why |
|---|---|
| `use_ws=Yes` (+ `ws_url`) | WebSocket transport available at `ws://host:port<ws_url>`. |
| `player_listen=Yes` **and** `player_ahear=Yes` | A **player** fires `AHEAR`. If off → run the relay on a **thing you own** instead and `oob(name(<botplayer>), …)` (same owner → permitted; things listen without these configs). |
| `side_effects=Yes` | `oob()` is a side-effect function; if disabled it's blocked server-wide. |
| `OOBTEST` returns a number (not `#-1`) | `oob()` and `json()` exist and you're permitted. `0` just means *this* connection isn't GMCP/WS — see below. |

**`OOBTEST=0` is normal when you probe over a non-GMCP client** (e.g. TinyFugue negotiates
`telnet` but not `gmcp`; `terminfo` will show neither `gmcp` nor `websocket`). `oob()` only
delivers to GMCP or WebSocket descriptors, so it has nowhere to land. This is a *client*
fact, not a server limitation — over WebSocket it delivers (`≥1`).

**Definitive proof** (connected over the real transport — WebSocket — not a plain client):

```
@listen me=*
&AHEAR me=@assert oob(name(me), Probe.Emit, json(object, from, json(string, name(%#)), dbref, json(string, %#), msg, json(string, %0)))
@create Tester
@force Tester=@emit SOLO-PROBE %ttab %rnewline
```

Expect on the JSON channel:
`{"from":"Tester","dbref":"#…","msg":"SOLO-PROBE \ttab \nnewline","gmcp":"Probe.Emit"}`

Teardown: `@wipe me/listen` · `@wipe me/ahear` · `@destroy Tester`.

---

## Setup: the relay attributes (installed once on the bot character)

```
@listen me=*
&AHEAR me=@assert oob(name(me), Room.Emit, json(object,
  from,  json(string, name(%#)),
  dbref, json(string, %#),
  msg,   json(string, %0)))
```

Notes that bit us during testing — bake them in:

- **`oob(name(me), …)`, never `oob(me, …)`.** `oob()` resolves arg 1 via `lookup_player()`,
  which takes a **player name or dbref** — it does *not* understand the `me` keyword
  (`oob(me,…)` → `#-1 NO MATCH`).
- **`@listen me=*` is greedy.** It relays *everything* the bot hears — room emits, poses,
  says, **and channel chatter / connect-disconnect spam**, each tagged with the enactor.
  Scope it: narrow the `@listen` pattern, add `@filter`/`@infilter`, or dispatch on the
  payload downstream. Don't ship `*` unfiltered.
- `@assert` just evaluates `oob()` for its side effect (and harmlessly stops the action
  list if delivery returned 0). No output is produced in-band.

### Richer envelope (recommended for cricket)

The minimal payload guarantees **attribution + isolation**, but not message *kind*. `%0` is
the *rendered* line (`Bob says, "hi"` / `<Public> Bob poses …`), so say/pose/emit/channel
still has to be inferred from the text — **but only for typing, never for attribution**
(the trusted speaker is always `dbref`). Consider enriching:

```
&AHEAR me=@assert oob(name(me), Room.Emit, json(object,
  from,  json(string, name(%#)),
  dbref, json(string, %#),
  loc,   json(string, loc(%#)),
  ts,    json(number, secs()),
  msg,   json(string, %0)))
```

Use distinct **package labels** to let the bot route without sniffing text — e.g. a
separate channel-listen attribute that emits `oob(name(me), Chan.Msg, …)`.

---

## The WebSocket transport

PennMUSH multiplexes channels **inside** the WS text payload. **Payload byte 0 is a channel
char**; the rest is data.

| Channel byte | Meaning |
|---|---|
| `t` | TEXT — ordinary rendered output (and the bot's own command echoes) |
| `j` | JSON — `oob()` / structured data ← **the event bus** |
| `p` | PUEBLO — HTML markup tags |
| `>` | PROMPT |

### Handshake

Standard RFC 6455 to `ws://host:port/wsclient` — the server matches the request line
`GET /wsclient HTTP/1.1` and the `Sec-WebSocket-Key` header. No subprotocol required. Any
mainstream client library (`websockets`, `websocket-client`) works. **No TLS unless the
server sets `ssl_port`** — then use `wss://`; otherwise login + all traffic is plaintext.

### Output (server → client)

Unmasked text frames. Read `payload[0]` as the channel char, `payload[1:]` as the body.
World events arrive on **`j`**; the bot's solicited command output arrives on **`t`**.

### Input (client → server)

Standard **masked** text frames (libraries mask automatically), with the payload
**prefixed by `t` (TEXT channel) and terminated by a newline**:

```
ws.send("t" + "connect Cricket <pw>" + "\r\n")
ws.send("t" + "@emit Hello" + "\r\n")
```

Without the `t` channel byte the server **ignores** the frame; without the trailing
newline the command never leaves the input cooker. Both were dead-ends until fixed.

### Verify the connection negotiated WS

After login: `think terminfo(me)` → the list includes `websocket`.

---

## Message envelope (JSON channel)

`oob(player, package, data)` sends `data` (a JSON object). For WebSocket delivery the server
adds the package name under a **`gmcp`** key (`send_websocket_object`). So a frame on the
`j` channel looks like:

```json
{"from":"Bob","dbref":"#5","msg":"MARK_START \tTAB \nNEWLINE … MARK_END","gmcp":"Room.Emit"}
```

- `gmcp` — the package label (your routing key: `Room.Emit`, `Chan.Msg`, …).
- `dbref` — **trusted** speaker dbref (`%#`). Use this for identity/permission decisions.
- `from` — speaker name at emit time (display only; names change, dbrefs don't).
- `msg` — the rendered text, control chars escaped. Parse for *kind* only, never identity.

Over **GMCP** (telnet) the same object arrives as a telnet subnegotiation
(`IAC SB 201 <package> <space> <json> IAC SE`) **without** the `gmcp` key (the package is
the subneg header instead). The bot's transport choice (WS vs GMCP) only changes the
framing, not the payload — pick WebSocket as the happy path; it needs no in-client GMCP
negotiation (which TinyFugue and many libs lack).

---

## Integration with cricket

- **JSON channel `j` is the event bus.** Map each object → a `MushEvent`
  (`ChannelMessage`/`RoomSay`/…): `speaker_dbref` ← `dbref` (trusted), `speaker` ← `from`,
  `text`/`kind`/`channel` derived from `msg` + `gmcp` package. This retires the fragile
  regex-attribution in `mush/protocol.py` for heard traffic.
- **TEXT channel `t` is noise + solicited responses.** Ambient world traffic is *also*
  delivered in-band on `t` (the bot still hears it normally) — **ignore TEXT world traffic
  and process events from `j` only**, to avoid double-handling. Reserve `t` parsing for
  output the bot explicitly solicits (e.g. `look`, `@sweep`), and frame those with
  `OUTPUTPREFIX`/`OUTPUTSUFFIX` so you know which `t` belongs to your command.
- **Outbound is unchanged.** Send `say`/`pose`/`@emit`/`page` as `t`-channel input frames.
- **One socket, both directions** — WebSocket can carry commands out and events in; no
  separate telnet connection needed.

---

## Limitations / threat model

- **Plaintext without TLS.** If the server's `ssl_port=0`, login and all relayed content
  are in the clear. Use `wss://` only if `ssl_port` is set; otherwise restrict to
  trusted/LAN networks.
- **`%0` typing is still inference.** Attribution is guaranteed; say-vs-pose-vs-emit is not
  — derive it from text format, but never trust text for *who*.
- **Greedy listen.** `@listen me=*` mirrors all heard traffic; scope/filter it.
- **GMCP needs a capable client.** Plain TinyFugue won't receive OOB; WebSocket avoids the
  issue. (`oob()` returns `0` when no GMCP/WS descriptor is connected — not an error.)
- **Server prerequisites** (above) must hold: `use_ws`, `player_listen`+`player_ahear`
  (or a thing listener), `function_side_effects`, and `oob()`/`json()` present.

---

## Teardown

```
@wipe me/listen
@wipe me/ahear
```

(`&LISTEN me=` / `&AHEAR me=` empties the *values* but leaves the attribute names defined;
`@wipe` removes them outright.)

---

## Verified source references (PennMUSH)

- `fun_oob` — `src/bsd.c` (`lookup_player(args[0])`; permission `Can_Send_OOB` =
  Wizard ∨ `SEND_OOB` power, **or same owner**; iterates `CONN_GMCP` / `CONN_WEBSOCKETS`).
- `send_oob` (telnet GMCP, opt **201**) / `send_websocket_object` (adds `gmcp` key) —
  `src/bsd.c`, `src/websock.c`.
- WS channel routing & framing — `to_websocket_frame` / `process_websocket_frame`,
  `src/websock.c` (payload byte 0 = channel; input must be `t` channel).
- `AHEAR`/`AMHEAR`/`AAHEAR` speaker split (`speaker != target` → `AHEAR`) and
  `PLAYER_LISTEN`/`PLAYER_AHEAR` gating — `src/notify.c`.
- `json()` builder — `src/funjson.c`. `terminfo()` capability list — `src/bsd.c`.
