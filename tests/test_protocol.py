"""Protocol + BridgeClient round-trip test against a fake TCP bridge."""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest

from fl_studio_mcp.bridge_client import BridgeClient
from fl_studio_mcp.protocol import pack, read_frame


class FakeBridge:
    """Minimal echo server with per-action fake responses."""

    def __init__(self, port: int = 19876):
        self.port = port
        self.sock = None
        self.thread = None
        self.responses: dict[str, object] = {
            "meta.ping": {"ok": True, "bridge_version": "fake-0.1"},
            "transport.status": {"is_playing": False, "bpm": 140.0},
        }

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", self.port))
        self.sock.listen(1)
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        try:
            conn, _ = self.sock.accept()
            conn.settimeout(5.0)
            while True:
                try:
                    req = read_frame(conn)
                except Exception:
                    return
                action = req.get("action", "")
                if action in self.responses:
                    conn.sendall(pack({
                        "id": req["id"], "ok": True, "result": self.responses[action]
                    }))
                elif action == "raise.me":
                    conn.sendall(pack({
                        "id": req["id"], "ok": False, "error": "boom"
                    }))
                else:
                    conn.sendall(pack({
                        "id": req["id"], "ok": True, "result": {"echo": req.get("params", {})}
                    }))
        except Exception:
            pass

    def stop(self):
        if self.sock:
            self.sock.close()


@pytest.fixture
def bridge():
    b = FakeBridge()
    b.start()
    time.sleep(0.05)
    yield b
    b.stop()


def test_ping_roundtrip(bridge):
    c = BridgeClient(port=bridge.port)
    r = c.ping()
    assert r["ok"] is True
    assert r["bridge_version"] == "fake-0.1"


def test_echo_params(bridge):
    c = BridgeClient(port=bridge.port)
    r = c.call("anything.else", foo=1, bar="baz")
    assert r == {"echo": {"foo": 1, "bar": "baz"}}


def test_error_propagated(bridge):
    c = BridgeClient(port=bridge.port)
    with pytest.raises(Exception) as exc:
        c.call("raise.me")
    assert "boom" in str(exc.value)


def test_reconnect_after_drop():
    """Verify the client lazy-reconnects to a freshly-started bridge on the same port."""
    b = FakeBridge(port=19877)
    b.start()
    time.sleep(0.05)
    c = BridgeClient(port=19877, timeout=2.0)
    c.ping()
    b.stop()
    c.close()  # force the stale fd to drop
    # restart with a FRESH bridge on the same port
    b2 = FakeBridge(port=19877)
    b2.start()
    time.sleep(0.05)
    r = c.ping()
    assert r["ok"] is True
    b2.stop()


def test_raises_when_bridge_unreachable():
    """Fresh client with no bridge listening should raise a clear error."""
    c = BridgeClient(port=19999, timeout=0.5)
    with pytest.raises(Exception) as exc:
        c.ping()
    msg = str(exc.value).lower()
    assert "bridge unavailable" in msg or "refused" in msg or "connection" in msg
