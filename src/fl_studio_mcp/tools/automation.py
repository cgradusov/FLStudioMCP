"""Parameter automation via processRECEvent (records live automation clips)."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ..bridge_client import get_client


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def automation_record_tempo(points: list[dict]) -> dict:
        """Record an automation ramp on the master tempo.

        `points`: list of {time_bars: float, bpm: float}. MCP will sequence them live
        with the correct REC flags to create a real automation clip."""
        return get_client().call("automation.recordTempo", points=points)

    @mcp.tool()
    def automation_record_channel_volume(channel: int, points: list[dict]) -> dict:
        """Record volume automation on a channel. `points`: [{time_bars, value}]."""
        return get_client().call("automation.recordChannelVolume", channel=channel, points=points)

    @mcp.tool()
    def automation_record_channel_pan(channel: int, points: list[dict]) -> dict:
        """Record pan automation on a channel."""
        return get_client().call("automation.recordChannelPan", channel=channel, points=points)

    @mcp.tool()
    def automation_record_mixer_volume(track: int, points: list[dict]) -> dict:
        """Record volume automation on a mixer track."""
        return get_client().call("automation.recordMixerVolume", track=track, points=points)

    @mcp.tool()
    def automation_record_plugin_param(channel: int,
                                       param: int,
                                       points: list[dict],
                                       slot: int = -1,
                                       location: Literal["channel", "mixer"] = "channel") -> dict:
        """Record automation on a plugin parameter. `points`: [{time_bars, value}]."""
        return get_client().call("automation.recordPluginParam",
                                 channel=channel, param=param, slot=slot,
                                 location=location, points=points)
