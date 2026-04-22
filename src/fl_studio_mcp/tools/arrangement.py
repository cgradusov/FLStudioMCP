"""Arrangement management (multi-arrangement projects)."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..bridge_client import get_client


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def arrangement_current() -> dict:
        """Return current arrangement index + name."""
        return get_client().call("arrangement.current")

    @mcp.tool()
    def arrangement_list() -> dict:
        """List all arrangements."""
        return get_client().call("arrangement.list")

    @mcp.tool()
    def arrangement_select(index: int) -> dict:
        """Switch to a different arrangement."""
        return get_client().call("arrangement.select", index=index)

    @mcp.tool()
    def arrangement_jump_marker(direction: int = 1) -> dict:
        """Jump playhead to next (+1) or previous (-1) marker within current arrangement."""
        return get_client().call("arrangement.jumpMarker", direction=direction)

    @mcp.tool()
    def arrangement_play_time() -> dict:
        """Get current playback time in ticks + bars + seconds."""
        return get_client().call("arrangement.playTime")
