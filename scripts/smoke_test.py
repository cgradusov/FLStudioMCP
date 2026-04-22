"""Quick smoke test — runs against a live FL Studio instance with the bridge loaded.

    > python scripts/smoke_test.py
"""
from __future__ import annotations

import sys
import time

from fl_studio_mcp.bridge_client import get_client


def section(name: str):
    print(f"\n=== {name} ===")


def main() -> int:
    try:
        client = get_client()
        info = client.ping()
        print("PING:", info)
    except Exception as e:
        print("Bridge unreachable:", e)
        print("Is FL Studio open and the 'fLMCP Bridge' MIDI device enabled?")
        return 1

    section("Project metadata")
    print(client.call("project.metadata"))

    section("Transport status")
    print(client.call("transport.status"))

    section("Channels (first 5)")
    all_ch = client.call("channels.all")
    for c in all_ch.get("channels", [])[:5]:
        print(f"  {c['index']:>2}  {c['name']}")

    section("Mixer (first 5 named)")
    m = client.call("mixer.allTracks", include_empty=False)
    for t in m.get("tracks", [])[:5]:
        print(f"  {t['index']:>2}  {t['name']}  vol={t['volume']:.2f}")

    section("Patterns")
    for p in client.call("patterns.list").get("patterns", [])[:5]:
        print(f"  {p['index']:>2}  {p['name']}")

    section("Tempo ramp (100 -> 140 BPM)")
    start = time.monotonic()
    for bpm in (100, 110, 120, 130, 140):
        client.call("transport.setTempo", bpm=bpm)
        time.sleep(0.2)
    print(f"  done in {time.monotonic()-start:.1f}s")

    print("\nSmoke test OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
