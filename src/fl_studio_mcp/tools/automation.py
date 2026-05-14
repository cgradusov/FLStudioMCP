"""Parameter automation via processRECEvent (records live automation clips)."""

from __future__ import annotations

import math
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ..bridge_client import get_client


def _shape_points(shape: str, start: float, end: float, length_bars: float,
                  resolution: int, rate_hz: float, bpm: float) -> list[dict]:
    """Translate a high-level shape descriptor into [{time_bars, value}, ...]."""
    pts: list[dict] = []
    n = max(2, int(resolution))
    for i in range(n):
        u = i / (n - 1)  # 0..1
        t = u * length_bars
        if shape == "linear":
            v = start + (end - start) * u
        elif shape in ("ease", "ease_in_out"):
            s = 0.5 - 0.5 * math.cos(math.pi * u)
            v = start + (end - start) * s
        elif shape == "exp":
            # exponential ramp from start->end (slow-then-fast)
            s = (math.exp(3 * u) - 1) / (math.exp(3) - 1)
            v = start + (end - start) * s
        elif shape == "sine":
            # LFO around midpoint (start = center, end = peak amplitude)
            center = start
            amp = end
            beats = length_bars * 4.0
            cycles = rate_hz * (60.0 / max(1e-6, bpm)) * beats
            v = center + amp * math.sin(2 * math.pi * cycles * u)
        elif shape == "saw":
            beats = length_bars * 4.0
            cycles = rate_hz * (60.0 / max(1e-6, bpm)) * beats
            phase = (cycles * u) % 1.0
            v = start + (end - start) * phase
        elif shape == "square":
            beats = length_bars * 4.0
            cycles = rate_hz * (60.0 / max(1e-6, bpm)) * beats
            phase = (cycles * u) % 1.0
            v = start if phase < 0.5 else end
        else:
            v = start + (end - start) * u
        pts.append({"time_bars": t, "value": max(0.0, min(1.0, v))})
    return pts


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def automation_shape_points(shape: Literal["linear", "ease", "exp", "sine", "saw", "square"],
                                start: float,
                                end: float,
                                length_bars: float,
                                resolution: int = 32,
                                rate_hz: float = 1.0,
                                bpm: float = 140.0) -> dict:
        """Generate [{time_bars, value}] for a common automation shape.

        Pipe the result straight into `automation_record_*`. Values are clamped to 0..1.

        - linear/ease/exp: ramp from `start` to `end` over `length_bars`.
        - sine: LFO with center=`start`, amplitude=`end`, frequency `rate_hz`.
        - saw/square: cyclic shapes between `start` and `end` at `rate_hz`.
        """
        return {"points": _shape_points(shape, start, end, length_bars, resolution, rate_hz, bpm)}

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
