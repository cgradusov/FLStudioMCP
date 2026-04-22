"""Send Ctrl+Alt+Y to the FL Studio window to fire the companion piano-roll pyscript.

Strategy: find the FL Studio foreground window, bring it to front, send the
hotkey via Win32 SendInput. Requires pywin32 on Windows; on other platforms
falls back to a no-op and relies on user pressing the hotkey manually.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

log = logging.getLogger("fl_studio_mcp.keystroke")

HOTKEY_NAME = "Ctrl+Alt+Y (Win) / Cmd+Opt+Y (Mac)"

_PR_REQUEST_FILE = Path(os.path.expandvars(
    r"%USERPROFILE%\Documents\Image-Line\FL Studio\Settings\Piano roll scripts\fLMCP_request.json"
)) if sys.platform == "win32" else Path.home() / "Documents/Image-Line/FL Studio/Settings/Piano roll scripts/fLMCP_request.json"

_PR_STATE_FILE = _PR_REQUEST_FILE.with_name("fLMCP_state.json")


def request_file() -> Path:
    return _PR_REQUEST_FILE


def state_file() -> Path:
    return _PR_STATE_FILE


def clear_state() -> None:
    try:
        if _PR_STATE_FILE.exists():
            _PR_STATE_FILE.unlink()
    except Exception:
        pass


def wait_for_state(deadline_sec: float = 3.0) -> dict | None:
    """Poll for the state file produced by the piano-roll pyscript."""
    import json
    end = time.monotonic() + deadline_sec
    while time.monotonic() < end:
        if _PR_STATE_FILE.exists():
            try:
                return json.loads(_PR_STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        time.sleep(0.05)
    return None


def send_hotkey_windows() -> bool:
    """Find FL Studio window and send Ctrl+Alt+Y. Returns True on success."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        import ctypes.wintypes as w

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        # 1) Find FL Studio window
        target_hwnd = [0]

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, w.HWND, w.LPARAM)

        def _enum(hwnd, _):
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return 1
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if "FL Studio" in title and user32.IsWindowVisible(hwnd):
                target_hwnd[0] = hwnd
                return 0
            return 1

        user32.EnumWindows(WNDENUMPROC(_enum), 0)
        if not target_hwnd[0]:
            log.warning("FL Studio window not found for keystroke")
            return False

        # 2) Bring to foreground (best effort)
        user32.ShowWindow(target_hwnd[0], 9)  # SW_RESTORE
        user32.SetForegroundWindow(target_hwnd[0])
        time.sleep(0.08)

        # 3) SendInput key combo Ctrl+Alt+Y
        # Virtual key codes
        VK_CONTROL = 0x11
        VK_MENU = 0x12  # alt
        VK_Y = 0x59
        KEYEVENTF_KEYUP = 0x0002
        INPUT_KEYBOARD = 1

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                        ("time", w.DWORD), ("dwExtraInfo", ctypes.POINTER(w.ULONG))]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
                        ("dwFlags", w.DWORD), ("time", w.DWORD),
                        ("dwExtraInfo", ctypes.POINTER(w.ULONG))]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]

        class _UNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", w.DWORD), ("u", _UNION)]

        def make_input(vk, up=False):
            i = INPUT()
            i.type = INPUT_KEYBOARD
            i.u.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, None)
            return i

        seq = [
            make_input(VK_CONTROL, up=False),
            make_input(VK_MENU, up=False),
            make_input(VK_Y, up=False),
            make_input(VK_Y, up=True),
            make_input(VK_MENU, up=True),
            make_input(VK_CONTROL, up=True),
        ]
        arr = (INPUT * len(seq))(*seq)
        user32.SendInput.argtypes = (w.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        sent = user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))
        return sent == len(seq)
    except Exception as e:
        log.warning("keystroke failed: %s", e)
        return False
