"""Pattern create / rename / select / clone / delete / length / color."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..bridge_client import get_client


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def pattern_count() -> dict:
        """Return total pattern count."""
        return get_client().call("patterns.count")

    @mcp.tool()
    def pattern_current() -> dict:
        """Return index + name of currently selected pattern."""
        return get_client().call("patterns.current")

    @mcp.tool()
    def pattern_list() -> dict:
        """Return list of all patterns: [{index, name, color, length}]."""
        return get_client().call("patterns.list")

    @mcp.tool()
    def pattern_select(index: int) -> dict:
        """Jump to pattern by index (1-based in FL)."""
        return get_client().call("patterns.select", index=index)

    @mcp.tool()
    def pattern_create(name: str = "") -> dict:
        """Create a new empty pattern. Returns {index, name}."""
        return get_client().call("patterns.create", name=name)

    @mcp.tool()
    def pattern_rename(index: int, name: str) -> dict:
        """Rename an existing pattern."""
        return get_client().call("patterns.rename", index=index, name=name)

    @mcp.tool()
    def pattern_set_color(index: int, color: str) -> dict:
        """Set pattern color. Accepts '#RRGGBB' or 'rgb(r,g,b)'."""
        return get_client().call("patterns.setColor", index=index, color=color)

    @mcp.tool()
    def pattern_clone(index: int, new_name: str = "") -> dict:
        """Clone a pattern (copy all notes & channel grid bits)."""
        return get_client().call("patterns.clone", index=index, new_name=new_name)

    @mcp.tool()
    def pattern_delete(index: int) -> dict:
        """Delete a pattern by index."""
        return get_client().call("patterns.delete", index=index)

    @mcp.tool()
    def pattern_set_length(index: int, bars: float) -> dict:
        """Set pattern length in bars."""
        return get_client().call("patterns.setLength", index=index, bars=bars)

    @mcp.tool()
    def pattern_find_by_name(name: str) -> dict:
        """Find a pattern by exact name (case-insensitive). Returns {index, name} or null."""
        return get_client().call("patterns.findByName", name=name)

    @mcp.tool()
    def pattern_jump_to_next() -> dict:
        """Select the next pattern in the list."""
        return get_client().call("patterns.jumpNext")

    @mcp.tool()
    def pattern_jump_to_previous() -> dict:
        """Select the previous pattern in the list."""
        return get_client().call("patterns.jumpPrev")
