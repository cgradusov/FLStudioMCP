"""
Thread-safe TCP client that talks to the FL Studio bridge script.

Owns a single persistent connection; serializes calls through a lock so the
MCP server's async tools can hit it concurrently without corrupting the frame
stream. Automatic lazy-reconnect. Sync API (MCP tools already run in worker
threads under `anyio.to_thread.run_sync`).
"""

from __future__ import annotations

import itertools
import logging
import socket
import threading
import time
from typing import Any

from .protocol import HOST, PORT, RPCError, pack, read_frame

log = logging.getLogger("fl_studio_mcp.bridge")


class BridgeClient:
    def __init__(self, host: str = HOST, port: int = PORT, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._ids = itertools.count(1)

    # ---- connection lifecycle -------------------------------------------------
    def _connect(self) -> socket.socket:
        s = socket.create_connection((self.host, self.port), timeout=self.timeout)
        s.settimeout(self.timeout)
        return s

    def _ensure(self) -> socket.socket:
        if self._sock is None:
            self._sock = self._connect()
        return self._sock

    def close(self) -> None:
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None

    def is_connected(self) -> bool:
        return self._sock is not None

    # ---- request/response -----------------------------------------------------
    def call(self, action: str, **params: Any) -> Any:
        req_id = next(self._ids)
        envelope = {"id": req_id, "action": action, "params": params}
        frame = pack(envelope)
        with self._lock:
            last_err: Exception | None = None
            for attempt in (1, 2):
                try:
                    sock = self._ensure()
                    sock.sendall(frame)
                    # drain async notifications until we see our response id
                    deadline = time.monotonic() + self.timeout
                    while True:
                        if time.monotonic() > deadline:
                            raise TimeoutError(f"no response for action={action}")
                        resp = read_frame(sock)
                        if resp.get("id") == req_id:
                            break
                        # ignore push notifications for now (future: dispatch)
                    if resp.get("ok"):
                        return resp.get("result")
                    raise RPCError(action=action, message=str(resp.get("error") or "unknown error"))
                except (ConnectionError, OSError, TimeoutError) as e:
                    last_err = e
                    log.warning("bridge call %s attempt %d failed: %s", action, attempt, e)
                    if self._sock is not None:
                        try:
                            self._sock.close()
                        except OSError:
                            pass
                        self._sock = None
                    if attempt == 2:
                        break
            raise RPCError(action=action, message=f"bridge unavailable: {last_err}")

    # ---- convenience ----------------------------------------------------------
    def ping(self) -> dict:
        return self.call("meta.ping")


_singleton: BridgeClient | None = None
_singleton_lock = threading.Lock()


def get_client() -> BridgeClient:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = BridgeClient()
        return _singleton
