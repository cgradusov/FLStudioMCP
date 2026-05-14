"""Project-level: new / open / save / render / undo / metadata."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP

from ..bridge_client import get_client


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def project_metadata() -> dict:
        """Project snapshot: tempo, signature, tracks, channels, patterns, selected, title, path."""
        return get_client().call("project.metadata")

    @mcp.tool()
    def project_new(template: Optional[str] = None) -> dict:
        """Start a new project (optionally from a template path)."""
        return get_client().call("project.new", template=template)

    @mcp.tool()
    def project_open(path: str) -> dict:
        """Open an existing .flp project."""
        return get_client().call("project.open", path=path)

    @mcp.tool()
    def project_save() -> dict:
        """Save the project."""
        return get_client().call("project.save")

    @mcp.tool()
    def project_save_as(path: str) -> dict:
        """Save the project to a new path."""
        return get_client().call("project.saveAs", path=path)

    @mcp.tool()
    def project_undo() -> dict:
        """Undo last action."""
        return get_client().call("project.undo")

    @mcp.tool()
    def project_redo() -> dict:
        """Redo last undone action."""
        return get_client().call("project.redo")

    @mcp.tool()
    def project_undo_history() -> dict:
        """Return undo history stack."""
        return get_client().call("project.undoHistory")

    @mcp.tool()
    def project_save_undo(name: str, flags: int = 0) -> dict:
        """Push a named entry onto the undo stack before a batch edit."""
        return get_client().call("project.saveUndo", name=name, flags=flags)

    @mcp.tool()
    def project_render(path: str,
                       format: Literal["wav", "mp3", "flac", "ogg"] = "wav",
                       mode: Literal["song", "pattern"] = "song") -> dict:
        """Open FL's render dialog (half-automated render).

        FL's Python API doesn't expose a true headless render from inside the
        controller script — the best in-process path is to fire FPT_Render
        (Ctrl+R) and have the user click Start. For fully automated batch
        rendering, use `project_render_cli` instead.
        """
        return get_client().call("project.render", path=path, format=format, mode=mode)

    @mcp.tool()
    def project_render_cli(flp_path: str,
                           output_path: str,
                           format: Literal["wav", "mp3", "flac", "ogg"] = "mp3",
                           fl_exe: Optional[str] = None) -> dict:
        """Render a .flp to audio by shelling out to FL64.exe in headless mode.

        This runs a separate FL Studio process — your interactive FL session is
        not affected. Save the project first (`project_save`) so the .flp on
        disk is up to date.

        `flp_path` and `output_path` should be absolute. `fl_exe` is
        auto-detected on Windows (Program Files / Image-Line / FL Studio 2025).
        """
        if not os.path.exists(flp_path):
            return {"ok": False, "error": f"flp not found: {flp_path}"}

        exe = fl_exe
        if not exe:
            candidates = [
                r"C:\Program Files\Image-Line\FL Studio 2025\FL64.exe",
                r"C:\Program Files\Image-Line\FL Studio 24\FL64.exe",
                r"C:\Program Files\Image-Line\FL Studio 21\FL64.exe",
                shutil.which("FL64.exe") or "",
                shutil.which("FL.exe") or "",
            ]
            exe = next((c for c in candidates if c and os.path.exists(c)), "")
        if not exe:
            return {"ok": False, "error": "FL64.exe not found; pass fl_exe explicitly"}

        # FL64.exe headless render flags:
        #   /R              render
        #   /F<format>      output format (wav/mp3/flac/ogg)
        #   /E<file>        explicit output file
        # Some FL versions use /Etrack or other variants — keep the common ones.
        cmd = [exe, "/R", f"/F{format}", f"/E{output_path}", flp_path]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "render timed out after 1h"}
        return {
            "ok": proc.returncode == 0 and Path(output_path).exists(),
            "returncode": proc.returncode,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
            "output": output_path if Path(output_path).exists() else None,
            "command": cmd,
        }

    @mcp.tool()
    def project_title() -> dict:
        """Best-effort access to FL's main-window title (often includes the .flp filename)."""
        return get_client().call("project.title")

    @mcp.tool()
    def project_version() -> dict:
        """Return FL Studio version string."""
        return get_client().call("project.version")
