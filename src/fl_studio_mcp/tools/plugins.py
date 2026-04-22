"""Plugin introspection + parameter control for both channel generators and mixer FX slots."""

from __future__ import annotations

from typing import Any, Literal, Optional

from mcp.server.fastmcp import FastMCP

from ..bridge_client import get_client


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def plugin_is_valid(index: int, slot: int = -1, location: Literal["channel", "mixer"] = "channel") -> dict:
        """Check if a plugin slot has a valid plugin loaded."""
        return get_client().call("plugins.isValid", index=index, slot=slot, location=location)

    @mcp.tool()
    def plugin_name(index: int, slot: int = -1, location: Literal["channel", "mixer"] = "channel") -> dict:
        """Plugin display name."""
        return get_client().call("plugins.name", index=index, slot=slot, location=location)

    @mcp.tool()
    def plugin_param_count(index: int, slot: int = -1, location: Literal["channel", "mixer"] = "channel") -> dict:
        """Return number of automatable parameters."""
        return get_client().call("plugins.paramCount", index=index, slot=slot, location=location)

    @mcp.tool()
    def plugin_params(index: int,
                      slot: int = -1,
                      location: Literal["channel", "mixer"] = "channel",
                      limit: int = 128,
                      offset: int = 0) -> dict:
        """List parameters (paginated): [{idx, name, value, value_string}]."""
        return get_client().call("plugins.params",
                                 index=index, slot=slot, location=location,
                                 limit=limit, offset=offset)

    @mcp.tool()
    def plugin_get_param(index: int, param: int,
                         slot: int = -1, location: Literal["channel", "mixer"] = "channel") -> dict:
        """Get value of a single parameter."""
        return get_client().call("plugins.getParam",
                                 index=index, param=param, slot=slot, location=location)

    @mcp.tool()
    def plugin_set_param(index: int, param: int, value: float,
                         slot: int = -1, location: Literal["channel", "mixer"] = "channel") -> dict:
        """Set a single parameter (0.0..1.0 normalised)."""
        return get_client().call("plugins.setParam",
                                 index=index, param=param, value=value,
                                 slot=slot, location=location)

    @mcp.tool()
    def plugin_find_param(index: int, name_contains: str,
                          slot: int = -1, location: Literal["channel", "mixer"] = "channel") -> dict:
        """Find a parameter by substring (case-insensitive)."""
        return get_client().call("plugins.findParam",
                                 index=index, name_contains=name_contains,
                                 slot=slot, location=location)

    @mcp.tool()
    def plugin_preset_count(index: int, slot: int = -1, location: Literal["channel", "mixer"] = "channel") -> dict:
        """Number of built-in presets for plugin."""
        return get_client().call("plugins.presetCount", index=index, slot=slot, location=location)

    @mcp.tool()
    def plugin_next_preset(index: int, slot: int = -1, location: Literal["channel", "mixer"] = "channel") -> dict:
        """Advance to the next preset."""
        return get_client().call("plugins.nextPreset", index=index, slot=slot, location=location)

    @mcp.tool()
    def plugin_prev_preset(index: int, slot: int = -1, location: Literal["channel", "mixer"] = "channel") -> dict:
        """Go back to the previous preset."""
        return get_client().call("plugins.prevPreset", index=index, slot=slot, location=location)

    @mcp.tool()
    def plugin_set_preset(index: int, preset: int,
                          slot: int = -1, location: Literal["channel", "mixer"] = "channel") -> dict:
        """Load preset by numeric index."""
        return get_client().call("plugins.setPreset",
                                 index=index, preset=preset, slot=slot, location=location)

    @mcp.tool()
    def plugin_show_editor(index: int, slot: int = -1, location: Literal["channel", "mixer"] = "channel",
                           show: Optional[bool] = None) -> dict:
        """Show/hide the plugin editor window (None = toggle)."""
        return get_client().call("plugins.showEditor",
                                 index=index, slot=slot, location=location, show=show)

    @mcp.tool()
    def plugin_list_mixer_track(track: int) -> dict:
        """List all loaded plugins in every FX slot of a mixer track."""
        return get_client().call("plugins.listMixerTrack", track=track)
