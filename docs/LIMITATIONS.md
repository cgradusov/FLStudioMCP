# fLMCP — Known limitations

All limits below come from FL Studio's public Python API ([FL Studio API Stubs
reference](https://il-group.github.io/FL-Studio-API-Stubs/)), not from fLMCP's
architecture. For each, the bridge returns a helpful error rather than
silently failing.

## Tool verification status

Tools are validated against the public API stubs. Legend:

- ✅ **verified** — function exists in the public stubs, signature matches,
  the bridge calls it correctly.
- ⚠️ **limited** — works, but only partially (e.g. toggle-only, no read-back).
- ❌ **not exposed** — the FL Python API does not provide this; the bridge
  returns a structured error explaining the workaround.

The tool *still appears* in the MCP catalog regardless, because Claude can use
the error response to fall back gracefully.

## Per-area limits

### Patterns
- ✅ create (`setPatternName` on new index), rename, select, list, color,
  clone, find-by-name, next/prev
- ❌ `pattern_delete` — FL has no `deletePattern()`. Bridge soft-deletes by
  emptying the name; pattern remains in the pool.
- ❌ `pattern_set_length` — not exposed; length is derived from notes / steps.

### Playlist
- ✅ track vol/pan/mute/solo/name/color
- ❌ `playlist_place_pattern`, `playlist_delete_clip`, `playlist_list_clips`
  — FL's public API has no clip-level accessors.
- ❌ `playlist_delete_marker` — not exposed.
- ⚠️ `playlist_add_marker` — works via `arrangement.addAutoTimeMarker`.
- ⚠️ `playlist_list_markers` — cannot enumerate; use
  `arrangement_jump_marker(+1/-1)` to step through.

### Arrangement
- ⚠️ `arrangement_jump_marker(direction)` — works (single function: `jumpToMarker`).
- ❌ `arrangement_select`, `arrangement_list`, `arrangement_current` —
  multi-arrangement switching is **not** exposed in the current stubs.

### Project
- ❌ `project_new`, `project_open`, `project_render` — require UI interaction.
- ✅ `project_save`, `project_save_as` — via `transport.globalTransport(FPT_Save)`.
- ✅ `project_undo` / `project_redo` via `general.undoUp/Down`.
- ⚠️ `project_undo_history` — returns `count / position / last / hint`
  (per-index entry names are not exposed by FL).
- ✅ `project_metadata`, `project_version` — version returned as both int and
  `major.minor.patch` string.

### Mixer EQ
- ✅ `mixer_get_eq`, `mixer_set_eq_band` — use the real API (`getEqGain`,
  `setEqGain`, `getEqFrequency`, `setEqFrequency`, `getEqBandwidth`).
- ✅ `mixer_route`, `mixer_set_send_level` — use `setRouteTo`,
  `setRouteToLevel`, `getRouteToLevel`, `afterRoutingChanged`.
- ✅ `mixer_select` — `setActiveTrack` (exclusive selection).

### Plugins
- ✅ `plugin_is_valid / name / params / get_param / set_param / presets /
  show_editor` — all map to the public API on already-loaded plugins.
- ❌ **Loading new plugins into a slot** — Browser drag-drop only. Ask the
  user to load once, then fLMCP fully automates the parameters.

### Piano roll
- ✅ add / delete / clear / read / quantize / transpose / humanize /
  duplicate — all via `flpianoroll.score`.
- ⚠️ Requires FL Studio to be the foreground window so `SendInput(Ctrl+Alt+Y)`
  lands. Bridge does best-effort `SetForegroundWindow`. If focus fails, tool
  response has `hotkey_sent: False` — ask user to press Ctrl+Alt+Y manually.
- ⚠️ Requires the **`ComposeWithLLM` pyscript to be the currently selected
  piano-roll script**. When FL first loads, open any pattern's piano roll,
  click the *scripts* dropdown (top-right of the piano roll), and pick
  `ComposeWithLLM` once. FL remembers the choice across sessions.

### Transport constants
The bridge gracefully degrades if specific `midi.FPT_*` / `midi.REC_*`
constants are missing in your FL build. Affected tools return `{ok: false,
error: "...not available"}` rather than raising.

- `transport_tap_tempo` needs `FPT_TapTempo`
- `transport_toggle_metronome` needs `FPT_Metronome`
- `transport_toggle_countdown_before_recording` needs `FPT_CountDown*`
- `transport_jog` needs `FPT_Jog`
- `transport_set_time_signature` needs `REC_MainTimeSigNum/Den`
- `project_save` needs `FPT_Save` (FL 20+ has this)

### TCP transport
- Single-connection at a time: multiple concurrent MCP clients will serialize
  through one TCP conn. This keeps FL's main thread predictable; typically
  fine since Claude is the only client.
- Bridge binds to `127.0.0.1:9876`. If another process holds that port,
  bridge's `OnInit` logs the bind error; clients then get `bridge unavailable`.

### OnIdle throughput
FL Studio's `OnIdle` fires roughly 10–30 Hz depending on workload (not
60 Hz). Each drain cycle processes up to 32 queued requests, so realistic
throughput is a few hundred calls/sec. Individual call latency is typically
15–80 ms round-trip.
