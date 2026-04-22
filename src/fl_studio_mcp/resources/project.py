"""MCP resources surfacing live FL Studio state as read-only URIs."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from ..bridge_client import get_client


def register(mcp: FastMCP) -> None:
    @mcp.resource("fl://status")
    def status() -> str:
        """Bridge + transport quick status."""
        try:
            info = get_client().ping()
            t = get_client().call("transport.status")
            return json.dumps({"bridge": info, "transport": t}, indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, indent=2)

    @mcp.resource("fl://project")
    def project() -> str:
        """Full project metadata: tempo, signature, channels, mixer, patterns, selection."""
        try:
            return json.dumps(get_client().call("project.metadata"), indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, indent=2)

    @mcp.resource("fl://transport")
    def transport() -> str:
        """Live transport state (is_playing, position, tempo, loop mode)."""
        try:
            return json.dumps(get_client().call("transport.status"), indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, indent=2)

    @mcp.resource("fl://channels")
    def channels() -> str:
        """Full channel rack as JSON."""
        try:
            return json.dumps(get_client().call("channels.all"), indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, indent=2)

    @mcp.resource("fl://mixer")
    def mixer() -> str:
        """All mixer tracks as JSON."""
        try:
            return json.dumps(get_client().call("mixer.allTracks", include_empty=False), indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, indent=2)

    @mcp.resource("fl://patterns")
    def patterns() -> str:
        """All patterns in the project."""
        try:
            return json.dumps(get_client().call("patterns.list"), indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, indent=2)

    @mcp.resource("fl://playlist")
    def playlist() -> str:
        """Playlist tracks + clips."""
        try:
            tracks = get_client().call("playlist.allTracks", include_empty=False)
            clips = get_client().call("playlist.listClips", track=None)
            markers = get_client().call("playlist.listMarkers")
            return json.dumps({"tracks": tracks, "clips": clips, "markers": markers}, indent=2)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, indent=2)
