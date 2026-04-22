# fLMCP — Architecture

## Components

1. **`fl-studio-mcp` (Python package)** — FastMCP server process launched by
   the MCP host (Claude Desktop / Claude Code). Stdio transport.
2. **FL bridge script** — `device_FLStudioMCP.py` loaded by FL Studio as a MIDI
   controller script. Runs a TCP listener in a background thread; command
   execution happens on FL's main thread (`OnIdle`) because the FL API is not
   thread-safe.
3. **Piano-roll pyscript** — `ComposeWithLLM.pyscript` installed in FL
   Studio's `Settings/Piano roll scripts/` folder. The only way to reach
   `flpianoroll.Note / score.addNote / score.deleteNote` from the Python
   environment.
4. **Keystroke bridge** — `src/fl_studio_mcp/keystroke.py` sends Ctrl+Alt+Y to
   FL via Win32 `SendInput` after the MCP server stages a piano-roll request
   file. This is how the device bridge reaches `flpianoroll` — it cannot
   import it directly.

## Wire protocol

Length-prefixed JSON over TCP 127.0.0.1:9876:

```
frame  = <uint32 big-endian length> <utf-8 JSON payload>
req    = {"id": int, "action": "mod.name", "params": {...}}
resp   = {"id": int, "ok": bool, "result": any, "error": str|null}
event  = {"event": "mod.name", "data": any}   # server push, no id
```

Events currently emitted by the bridge:

- `transport.tick`  (~2 Hz while transport is playing)
- `refresh`         (passes `flags` from `OnRefresh`)
- `projectLoad`     (from `OnProjectLoad`)

## Request lifecycle

```
 MCP tool ─► BridgeClient.call(action, **params)
          ─► socket.sendall(packed_frame)
                 │
      ┌──────────┴──────────────────────────────────────────────────────────┐
      │                             FL Studio                                │
      │                                                                      │
      │  _server_loop (daemon thread) ── accept ──► _serve_client (worker)  │
      │                                                │                     │
      │                                                ▼                     │
      │                                           _inbox.put((conn, req))    │
      │                                                                      │
      │  OnIdle():                                                           │
      │    drained = 0                                                       │
      │    while drained < 32:                                               │
      │        conn, req = _inbox.get_nowait()                               │
      │        result = _execute(req.action, req.params)                     │
      │        conn.sendall(pack({"id": req.id, "ok": True, "result": ...})) │
      │    (also pushes transport.tick every ~500ms)                         │
      └──────────────────────────────────────────────────────────────────────┘
          │
          ▼
 MCP tool reads response frame, extracts result, returns to Claude
```

## Piano-roll lifecycle

```
 MCP tool piano_roll_add_notes(channel, notes, pattern)
     │
     ▼
 bridge.pianoroll.addNotes:
     - patterns.jumpToPattern(pattern)
     - channels.selectOneChannel(channel)
     - ui.showWindow(widPianoRoll); ui.setFocused(widPianoRoll)
     - append JSON request to fLMCP_request.json
     - respond {"staged": True, "needs_keystroke": True}
     │
     ▼
 MCP tool:
     - keystroke.clear_state()
     - keystroke.send_hotkey_windows()
            │
            ▼  (SendInput Ctrl+Alt+Y to FL window)
     - FL fires ComposeWithLLM.pyscript.apply()
         - reads fLMCP_request.json
         - edits notes via flpianoroll
         - writes fLMCP_state.json
     - keystroke.wait_for_state()  ──► returns parsed state to Claude
```

## Threading notes

- The TCP server runs in a Python daemon thread. It cannot touch FL API.
- `_inbox` is a stdlib `queue.Queue` (thread-safe).
- `OnIdle()` runs on FL's main thread. It drains up to 32 queued requests per
  tick (FL idle fires at roughly 60 Hz, so throughput is >1000 calls/sec).
- Responses are written back directly from `OnIdle()` using `sendall()` —
  still runs on the FL main thread but blocking time is bounded by payload
  size and the socket is local; sub-millisecond in practice.

## Color handling

- Bridge accepts: `"#RRGGBB"`, `"rgb(r,g,b)"`, integer.
- Bridge returns: always `"#RRGGBB"`.
- FL Studio internal: `0xBBGGRR` integer.
