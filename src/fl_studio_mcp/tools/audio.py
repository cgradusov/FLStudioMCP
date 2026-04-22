"""Audio file analysis + DnB workflow tools.

- Analyze any audio file (MP3/WAV/FLAC/OGG): tempo, key, onsets, melody.
- Slice audio at onsets into separate WAVs (samples).
- Extract dominant melody from a song and push into FL piano roll.
- Generate Drum & Bass drum patterns (amen/think/modern) at 174 BPM.
- One-shot: `song_to_dnb_flip` — MP3 in → FL piano roll out with DnB drums
  + melody from the track, matched to detected key + target BPM.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP

from ..audio_analysis import (
    analyze_audio,
    slice_at_onsets,
)
from ..file_bridge import stage_and_run
from ..voice_to_midi import (
    Note,
    SCALE_INTERVALS,
    drop_low_confidence,
    notes_as_piano_roll,
    quantize as quantize_notes,
    snap_to_scale,
    transcribe_monophonic,
    transpose,
)


# -------- DnB drum patterns (MIDI drum-map, 32-step per 2 bars) ---------
# 32 steps = 8 beats = 2 bars at 4/4. Positions 0..31 = 16th-note grid.
# Classic amen break at 174 BPM sounds double-time, so 1 "bar" at 174 BPM
# contains 16 16ths, and most DnB loops are 2 bars long.

KICK, SNARE, CLHAT, OPHAT, CLAP, RIDE, CRASH = 36, 38, 42, 46, 39, 51, 49

_AMEN_2BAR: dict[int, list[int]] = {
    KICK:  [1,0,0,0, 0,0,1,0, 0,0,1,0, 0,0,0,0,  0,0,0,0, 0,0,1,0, 0,0,1,0, 0,0,0,0],
    SNARE: [0,0,0,0, 1,0,0,1, 0,1,0,0, 1,0,0,0,  0,0,0,0, 1,0,0,1, 0,1,0,0, 1,0,1,0],
    CLHAT: [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0,  1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0],
    RIDE:  [0,0,0,1, 0,0,0,0, 0,0,0,1, 0,0,0,0,  0,0,0,1, 0,0,0,0, 0,0,0,1, 0,0,0,0],
}

_THINK_2BAR: dict[int, list[int]] = {
    KICK:  [1,0,0,0, 0,0,0,0, 0,0,1,0, 0,0,0,0,  1,0,0,0, 0,0,0,0, 0,0,1,0, 0,0,0,0],
    SNARE: [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,1,0,  0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0],
    CLHAT: [1,1,1,1, 1,1,1,1, 1,1,1,1, 1,1,1,1,  1,1,1,1, 1,1,1,1, 1,1,1,1, 1,1,1,1],
    OPHAT: [0,0,0,0, 0,0,0,1, 0,0,0,0, 0,0,0,1,  0,0,0,0, 0,0,0,1, 0,0,0,0, 0,0,0,1],
}

_MODERN_2BAR: dict[int, list[int]] = {
    KICK:  [1,0,0,0, 0,0,1,0, 0,0,0,0, 0,0,1,0,  0,0,1,0, 0,0,0,0, 0,0,1,0, 0,0,0,0],
    SNARE: [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0,  0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0],
    CLHAT: [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0,  1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0],
    OPHAT: [0,0,0,0, 0,0,0,0, 0,0,0,1, 0,0,0,0,  0,0,0,0, 0,0,0,0, 0,0,0,1, 0,0,0,0],
    RIDE:  [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,1,  0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,1],
}

_HALFTIME_2BAR: dict[int, list[int]] = {
    # "liquid / half-time" DnB feel, snare only on beat 3
    KICK:  [1,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0,  1,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0],
    SNARE: [0,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,0,  0,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,0],
    CLHAT: [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0,  1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0],
    OPHAT: [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,1,  0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,1],
}

DNB_STYLES: dict[str, dict[int, list[int]]] = {
    "amen":     _AMEN_2BAR,
    "think":    _THINK_2BAR,
    "modern":   _MODERN_2BAR,
    "halftime": _HALFTIME_2BAR,
}


def _dnb_drum_notes(style: str,
                    repeats: int,
                    step_bars: float = 0.0625) -> list[dict]:
    """Convert a 32-step DnB grid into piano-roll notes (2 bars per loop)."""
    grid = DNB_STYLES.get(style)
    if grid is None:
        raise ValueError(f"unknown DnB style: {style}; pick from {list(DNB_STYLES)}")
    notes: list[dict] = []
    rep = max(1, int(repeats))
    for r in range(rep):
        base_bar = r * 2  # each loop is 2 bars
        for midi_num, hits in grid.items():
            vel = 0.92 if midi_num == KICK else 0.85 if midi_num == SNARE else 0.65
            for step_idx, bit in enumerate(hits):
                if not bit:
                    continue
                t_bars = base_bar + step_idx * step_bars
                notes.append({
                    "midi": midi_num,
                    "time": t_bars * 4,  # pyscript expects quarter notes
                    "duration": step_bars * 4 * 0.95,
                    "velocity": vel,
                })
    return notes


def _reese_bass(key_root_midi: int, length_bars: float,
                step_bars: float = 0.25) -> list[dict]:
    """Simple DnB sub-bass pattern on the root."""
    notes: list[dict] = []
    total = max(1, int(length_bars / step_bars))
    for i in range(total):
        notes.append({
            "midi": key_root_midi,
            "time": i * step_bars * 4,
            "duration": step_bars * 4 * 0.9,
            "velocity": 0.88,
        })
    return notes


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def audio_analyze(path: str, extract_melody: bool = False) -> dict:
        """Analyze an audio file: tempo, key, onsets, loudness, (optional) melody.

        Accepts any format libsndfile supports: WAV, FLAC, MP3, OGG, AIFF...
        Returns BPM, detected key (root + major/minor), beat + onset timings,
        and optionally a monophonic melody transcription.
        """
        if not os.path.exists(path):
            return {"ok": False, "error": f"file not found: {path}"}
        a = analyze_audio(path, extract_melody=extract_melody)
        return {"ok": True, **a.as_dict(),
                "melody_notes": [{"midi": n.midi, "start_sec": n.start_sec,
                                  "duration_sec": n.duration_sec,
                                  "velocity": n.velocity,
                                  "confidence": n.confidence}
                                 for n in a.notes] if extract_melody else []}

    @mcp.tool()
    def audio_slice(path: str, output_dir: str | None = None,
                    max_slices: int = 32) -> dict:
        """Slice audio at detected onsets; save each slice as WAV on disk.

        Great for chopping a drum loop or sampled track into one-shots you
        can drag into FL's channel rack as sampler voices.
        """
        if not os.path.exists(path):
            return {"ok": False, "error": f"file not found: {path}"}
        slices = slice_at_onsets(path, output_dir=output_dir,
                                 max_slices=max_slices)
        return {"ok": True, "slices": slices, "count": len(slices)}

    @mcp.tool()
    def audio_melody_to_piano_roll(path: str,
                                   bpm: float | None = None,
                                   snap_to_detected_key: bool = True,
                                   transpose_semitones: int = 0,
                                   min_confidence: float = 0.3,
                                   clear_first: bool = True) -> dict:
        """Extract the dominant monophonic melody from an audio file and push
        it into the FL piano roll.

        If `bpm` is None, the detected BPM is used.  If `snap_to_detected_key`
        is True, all notes are snapped to the detected key of the track.
        """
        if not os.path.exists(path):
            return {"ok": False, "error": f"file not found: {path}"}

        a = analyze_audio(path, extract_melody=True)
        effective_bpm = float(bpm) if bpm else max(60.0, a.tempo_bpm or 120.0)

        ns = drop_low_confidence(a.notes, min_conf=min_confidence)
        if transpose_semitones:
            ns = transpose(ns, transpose_semitones)
        if snap_to_detected_key and a.key_root and a.key_scale in SCALE_INTERVALS:
            ns = snap_to_scale(ns, root=a.key_root, scale=a.key_scale)

        pr = notes_as_piano_roll(ns, bpm=effective_bpm)
        if not pr:
            return {"ok": False, "error": "no notes above confidence threshold",
                    "analysis": a.as_dict()}
        qn = [{"midi": n["midi"], "time": n["time_bars"] * 4,
               "duration": n["duration_bars"] * 4, "velocity": n["velocity"]}
              for n in pr]
        actions = ([{"action": "clear"}] if clear_first else []) + \
                  [{"action": "add_notes", "notes": qn}]
        res = stage_and_run(actions, wait_sec=8.0)
        return {"ok": res.get("ok", False),
                "notes_written": len(pr),
                "bpm_used": effective_bpm,
                "detected_key": f"{a.key_root} {a.key_scale}",
                "detected_bpm": round(a.tempo_bpm, 1),
                "piano_roll_state": res.get("state")}

    @mcp.tool()
    def gen_list_dnb_styles() -> dict:
        """Return available Drum & Bass drum pattern styles."""
        return {"styles": list(DNB_STYLES.keys())}

    @mcp.tool()
    def gen_emit_dnb_groove(style: Literal["amen", "think", "modern", "halftime"] = "modern",
                            repeats: int = 2,
                            clear_first: bool = True) -> dict:
        """Emit a Drum & Bass drum groove to the open piano roll as MIDI
        note-numbers (36 kick, 38 snare, 42 closed-hat, 46 open-hat, 51 ride).
        Each `repeat` is a 2-bar loop. Default 2 repeats = 4 bars.
        """
        notes = _dnb_drum_notes(style, repeats=repeats)
        actions = ([{"action": "clear"}] if clear_first else []) + \
                  [{"action": "add_notes", "notes": notes}]
        res = stage_and_run(actions, wait_sec=8.0)
        return {"ok": res.get("ok"), "notes_written": len(notes),
                "style": style, "bars": 2 * max(1, repeats),
                "piano_roll_state": res.get("state")}

    @mcp.tool()
    def song_to_dnb_flip(audio_path: str,
                         target_bpm: float = 174.0,
                         dnb_style: Literal["amen", "think", "modern", "halftime"] = "amen",
                         dnb_bars: int = 4,
                         include_melody: bool = True,
                         include_bass: bool = True,
                         clear_first: bool = True) -> dict:
        """One-shot: take any audio file and turn it into a DnB flip in the
        FL piano roll.

        Pipeline:
          1. Analyze the file (tempo, key, melody).
          2. Emit a DnB drum groove at `target_bpm`, `dnb_bars` bars long.
          3. (optional) Add the extracted melody, quantized to the detected
             key, on top.
          4. (optional) Drop in a sub-bass on the detected root.

        Note: everything is written into the currently-open piano roll
        (single channel). For a proper mix, duplicate the channel in FL and
        route by MIDI range (drums 36-51, bass < 40, melody > 55).
        """
        if not os.path.exists(audio_path):
            return {"ok": False, "error": f"file not found: {audio_path}"}
        a = analyze_audio(audio_path, extract_melody=include_melody)

        notes: list[dict] = []

        # 1) DnB drums at target_bpm (piano-roll time = bars anyway)
        notes.extend(_dnb_drum_notes(dnb_style, repeats=max(1, dnb_bars // 2)))

        # 2) Sub bass following the detected root
        if include_bass:
            from .generators import NOTE_NAMES
            if a.key_root in NOTE_NAMES:
                root_pc = NOTE_NAMES.index(a.key_root)
                # octave -1 for 808 sub (MIDI 12..23)
                root_midi = root_pc + 12 * 2   # C1..B1 range
                notes.extend(_reese_bass(root_midi, length_bars=float(dnb_bars)))

        # 3) Melody on top, at target_bpm-converted timing
        if include_melody and a.notes:
            ns = drop_low_confidence(a.notes, min_conf=0.3)
            ns = snap_to_scale(ns, root=a.key_root, scale=a.key_scale) \
                if a.key_scale in SCALE_INTERVALS else ns
            pr = notes_as_piano_roll(ns, bpm=target_bpm)
            for n in pr:
                # Only keep first `dnb_bars` bars so the melody fits the drum loop
                if n["time_bars"] < dnb_bars:
                    notes.append({
                        "midi": n["midi"],
                        "time": n["time_bars"] * 4,
                        "duration": n["duration_bars"] * 4,
                        "velocity": n["velocity"],
                    })

        actions = ([{"action": "clear"}] if clear_first else []) + \
                  [{"action": "add_notes", "notes": notes}]
        res = stage_and_run(actions, wait_sec=10.0)
        return {
            "ok": res.get("ok"),
            "notes_written": len(notes),
            "detected_bpm": round(a.tempo_bpm, 1),
            "detected_key": f"{a.key_root} {a.key_scale}",
            "target_bpm": target_bpm,
            "dnb_style": dnb_style,
            "dnb_bars": dnb_bars,
            "components": {
                "drums": True,
                "bass": include_bass,
                "melody": include_melody and bool(a.notes),
            },
            "hint": "Recommended: set FL project tempo to %d BPM. Duplicate "
                    "channel and route by MIDI range: drums 36-51, bass 12-28, "
                    "melody 40-90." % int(target_bpm),
            "piano_roll_state": res.get("state"),
        }
