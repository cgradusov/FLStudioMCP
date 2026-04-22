"""Smoke: the MCP server builds and registers the expected tool count."""
from __future__ import annotations


def test_build_app():
    from fl_studio_mcp.server import build_app
    app = build_app()
    tools = app._tool_manager.list_tools()
    assert len(tools) >= 130, f"expected >= 130 tools, got {len(tools)}"
    names = {t.name for t in tools}
    # Spot-check coverage across every module
    for required in [
        "fl_ping",
        "transport_play", "transport_set_tempo", "transport_set_time_signature",
        "pattern_create", "pattern_clone",
        "channel_set_step_sequence", "channel_quick_quantize",
        "mixer_set_volume", "mixer_set_eq_band", "mixer_route",
        "plugin_find_param", "plugin_list_mixer_track",
        "piano_roll_add_notes", "piano_roll_add_arpeggio", "piano_roll_humanize",
        "playlist_add_marker",
        "arrangement_select",
        "automation_record_tempo", "automation_record_plugin_param",
        "project_save", "project_undo", "project_render",
        "ui_show_window", "ui_hint",
        "gen_emit_chord_progression",
        "gen_emit_drum_pattern_notes", "gen_emit_drum_pattern_step_seq",
        "gen_emit_bassline", "gen_emit_melody", "gen_emit_arpeggio",
        "piano_roll_status",
    ]:
        assert required in names, f"missing tool: {required}"


def test_resources_registered():
    from fl_studio_mcp.server import build_app
    app = build_app()
    uris = {str(r.uri) for r in app._resource_manager.list_resources()}
    for required in ["fl://status", "fl://project", "fl://transport",
                     "fl://channels", "fl://mixer", "fl://patterns", "fl://playlist"]:
        assert required in uris, f"missing resource: {required}"
