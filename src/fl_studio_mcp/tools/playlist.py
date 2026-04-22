"""Playlist: track CRUD, clip placement, markers, live mode."""

from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from ..bridge_client import get_client


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def playlist_track_count() -> dict:
        """Playlist track count."""
        return get_client().call("playlist.trackCount")

    @mcp.tool()
    def playlist_track_info(track: int) -> dict:
        """Info on a playlist track: name, color, mute, solo, height, group."""
        return get_client().call("playlist.trackInfo", track=track)

    @mcp.tool()
    def playlist_all_tracks(include_empty: bool = False) -> dict:
        """List of all playlist tracks."""
        return get_client().call("playlist.allTracks", include_empty=include_empty)

    @mcp.tool()
    def playlist_set_track_name(track: int, name: str) -> dict:
        """Rename a playlist track."""
        return get_client().call("playlist.setTrackName", track=track, name=name)

    @mcp.tool()
    def playlist_set_track_color(track: int, color: str) -> dict:
        """Set playlist track color ('#RRGGBB')."""
        return get_client().call("playlist.setTrackColor", track=track, color=color)

    @mcp.tool()
    def playlist_mute_track(track: int, muted: Optional[bool] = None) -> dict:
        """Mute/unmute a playlist track."""
        return get_client().call("playlist.muteTrack", track=track, muted=muted)

    @mcp.tool()
    def playlist_solo_track(track: int, solo: Optional[bool] = None) -> dict:
        """Solo a playlist track."""
        return get_client().call("playlist.soloTrack", track=track, solo=solo)

    @mcp.tool()
    def playlist_list_clips(track: int | None = None) -> dict:
        """List all clips in the playlist (optionally filter to one track)."""
        return get_client().call("playlist.listClips", track=track)

    @mcp.tool()
    def playlist_place_pattern(track: int, pattern: int, position_bars: float, length_bars: float | None = None) -> dict:
        """Place a pattern clip on a playlist track at a given bar position."""
        return get_client().call("playlist.placePattern",
                                 track=track, pattern=pattern,
                                 position_bars=position_bars, length_bars=length_bars)

    @mcp.tool()
    def playlist_delete_clip(track: int, position_bars: float) -> dict:
        """Delete the clip on a track starting at the given bar position."""
        return get_client().call("playlist.deleteClip", track=track, position_bars=position_bars)

    @mcp.tool()
    def playlist_refresh() -> dict:
        """Force playlist repaint (use after bulk edits)."""
        return get_client().call("playlist.refresh")

    @mcp.tool()
    def playlist_list_markers() -> dict:
        """Return all timeline markers: [{pos_bars, name, mode}]."""
        return get_client().call("playlist.listMarkers")

    @mcp.tool()
    def playlist_add_marker(position_bars: float, name: str = "") -> dict:
        """Add a playlist marker."""
        return get_client().call("playlist.addMarker", position_bars=position_bars, name=name)

    @mcp.tool()
    def playlist_delete_marker(index: int) -> dict:
        """Remove a playlist marker by index."""
        return get_client().call("playlist.deleteMarker", index=index)
