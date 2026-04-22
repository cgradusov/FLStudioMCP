"""Voice-to-MIDI tools: hum a melody, transcribe it, send it to the piano roll.

Workflow:
    voice_list_devices()                 # optional — inspect mics
    voice_record_and_transcribe(8)       # 8-second capture -> MIDI notes
    voice_to_piano_roll(8, bpm=120, scale_root="C", scale="minor")
                                         # one-shot: capture + transcribe
                                         # + snap-to-scale + quantize +
                                         # write into the piano roll
"""

from __future__ import annotations

from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP

from ..file_bridge import stage_and_run
from ..voice_to_midi import (
    Note,
    SCALE_INTERVALS,
    drop_low_confidence,
    list_input_devices,
    notes_as_piano_roll,
    quantize,
    record_wav,
    snap_to_scale,
    transcribe_monophonic,
    transpose,
)


def _notes_to_dicts(notes: list[Note]) -> list[dict]:
    return [{
        "midi": n.midi,
        "start_sec": n.start_sec,
        "duration_sec": n.duration_sec,
        "velocity": n.velocity,
        "confidence": n.confidence,
    } for n in notes]


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def voice_open_gui() -> dict:
        """Launch the interactive Voice-to-MIDI GUI (Dear PyGui window).

        Starts a subprocess so the MCP server doesn't block. The window has
        live waveform, live pitch detection, post-processing controls
        (scale snap / quantize / transpose / confidence filter) and a 'Send
        to FL Studio' button.
        """
        import subprocess
        import sys as _sys
        try:
            proc = subprocess.Popen(
                [_sys.executable, "-m", "fl_studio_mcp.gui_voice"],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                if _sys.platform == "win32" else 0,
            )
            return {"ok": True, "pid": proc.pid,
                    "hint": "GUI window opened in a separate process."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @mcp.tool()
    def voice_list_devices() -> dict:
        """List available microphones (indexes + names + default flag)."""
        return {"devices": list_input_devices()}

    @mcp.tool()
    def voice_record_and_transcribe(
        duration_sec: float = 8.0,
        device: int | None = None,
        min_note_sec: float = 0.08,
        fmin_hz: float = 65.0,
        fmax_hz: float = 1200.0,
    ) -> dict:
        """Record the mic for `duration_sec` seconds and transcribe the hummed melody.

        Returns raw notes + the temp WAV path. Use this when you want to inspect
        the transcription before touching the piano roll. 3 short + 1 long
        beep plays at start, 1 beep at stop.
        """
        wav = record_wav(duration_sec, device=device)
        notes = transcribe_monophonic(
            wav, fmin_hz=fmin_hz, fmax_hz=fmax_hz,
            min_note_sec=min_note_sec,
        )
        return {
            "wav_path": str(wav),
            "notes": _notes_to_dicts(notes),
            "count": len(notes),
        }

    @mcp.tool()
    def voice_transcribe_file(
        audio_path: str,
        min_note_sec: float = 0.08,
        fmin_hz: float = 65.0,
        fmax_hz: float = 1200.0,
    ) -> dict:
        """Transcribe an existing audio file (wav / flac / mp3 / ogg) into MIDI notes."""
        notes = transcribe_monophonic(
            audio_path, fmin_hz=fmin_hz, fmax_hz=fmax_hz,
            min_note_sec=min_note_sec,
        )
        return {
            "audio_path": audio_path,
            "notes": _notes_to_dicts(notes),
            "count": len(notes),
        }

    @mcp.tool()
    def voice_to_piano_roll(
        duration_sec: float = 8.0,
        bpm: float = 120.0,
        device: int | None = None,
        scale_root: Optional[str] = None,
        scale: Optional[str] = None,
        transpose_semitones: int = 0,
        quantize_grid_sec: Optional[float] = None,
        min_confidence: float = 0.35,
        min_note_sec: float = 0.08,
        clear_first: bool = True,
    ) -> dict:
        """Hum a melody into the mic, get it written straight into FL's piano roll.

        Args:
            duration_sec:   how long to record.
            bpm:            used to convert seconds -> bars. Match your FL tempo.
            device:         mic index (see voice_list_devices); None = default.
            scale_root:     e.g. "C", "F#", "Bb". If given, notes are snapped.
            scale:          e.g. "minor", "major", "dorian". One of
                            gen_list_scales. Used only when scale_root is given.
            transpose_semitones: shift all notes up/down after transcription.
            quantize_grid_sec: snap note starts to this grid (e.g. 0.125 = 1/32
                            at 120 BPM, 0.25 = 1/16, 0.5 = 1/8). None = off.
            min_confidence: drop notes where pyin was uncertain (0..1).
            min_note_sec:   drop notes shorter than this many seconds.
            clear_first:    clear the open piano roll before writing.

        Returns:
            {ok, notes_written, piano_roll_state, wav_path, transcription_count}
        """
        import time as _t

        t0 = _t.monotonic()
        wav = record_wav(duration_sec, device=device)
        t_rec = _t.monotonic() - t0

        t0 = _t.monotonic()
        notes = transcribe_monophonic(wav, min_note_sec=min_note_sec)
        t_trans = _t.monotonic() - t0

        notes = drop_low_confidence(notes, min_conf=min_confidence)

        if transpose_semitones:
            notes = transpose(notes, transpose_semitones)

        if scale_root and scale:
            if scale not in SCALE_INTERVALS:
                return {"ok": False,
                        "error": f"unknown scale '{scale}'; choose from "
                                 f"{list(SCALE_INTERVALS.keys())}"}
            notes = snap_to_scale(notes, root=scale_root, scale=scale)

        if quantize_grid_sec is not None and quantize_grid_sec > 0:
            notes = quantize(notes, grid_sec=quantize_grid_sec, strength=1.0)

        pr_notes = notes_as_piano_roll(notes, bpm=bpm)

        if not pr_notes:
            return {
                "ok": False,
                "notes_written": 0,
                "reason": "no valid notes transcribed — try humming louder / "
                          "check voice_list_devices, or lower min_confidence.",
                "wav_path": str(wav),
                "record_sec": round(t_rec, 2),
                "transcribe_sec": round(t_trans, 2),
            }

        actions = []
        if clear_first:
            actions.append({"action": "clear"})
        # Convert piano-roll bars to quarter notes (pyscript expects quarters)
        qn_notes = []
        for n in pr_notes:
            qn_notes.append({
                "midi": n["midi"],
                "time": n["time_bars"] * 4,
                "duration": n["duration_bars"] * 4,
                "velocity": n["velocity"],
            })
        actions.append({"action": "add_notes", "notes": qn_notes})

        result = stage_and_run(actions, wait_sec=8.0)
        return {
            "ok": result.get("ok", False),
            "notes_written": len(pr_notes),
            "transcription_count": len(notes),
            "wav_path": str(wav),
            "bpm": bpm,
            "scale": f"{scale_root} {scale}" if scale_root and scale else None,
            "piano_roll_state": result.get("state"),
            "record_sec": round(t_rec, 2),
            "transcribe_sec": round(t_trans, 2),
            "note_preview": pr_notes[:8],
            "hint": result.get("note"),
        }

    @mcp.tool()
    def voice_notes_to_piano_roll(
        notes: list[dict],
        bpm: float = 120.0,
        scale_root: Optional[str] = None,
        scale: Optional[str] = None,
        transpose_semitones: int = 0,
        clear_first: bool = True,
    ) -> dict:
        """Push an already-transcribed note list (from voice_record_and_transcribe)
        into the piano roll with optional scale snapping / transposition.

        Useful when you want Claude to inspect the raw transcription first,
        tweak it, then send a cleaned-up version.
        """
        typed = [Note(midi=int(n["midi"]),
                      start_sec=float(n["start_sec"]),
                      duration_sec=float(n["duration_sec"]),
                      velocity=float(n.get("velocity", 0.8)),
                      confidence=float(n.get("confidence", 1.0)))
                 for n in notes]

        if transpose_semitones:
            typed = transpose(typed, transpose_semitones)
        if scale_root and scale:
            typed = snap_to_scale(typed, root=scale_root, scale=scale)

        pr_notes = notes_as_piano_roll(typed, bpm=bpm)
        qn_notes = [{"midi": n["midi"], "time": n["time_bars"] * 4,
                     "duration": n["duration_bars"] * 4, "velocity": n["velocity"]}
                    for n in pr_notes]
        actions = ([{"action": "clear"}] if clear_first else []) + \
                  [{"action": "add_notes", "notes": qn_notes}]
        result = stage_and_run(actions, wait_sec=8.0)
        return {
            "ok": result.get("ok", False),
            "notes_written": len(pr_notes),
            "piano_roll_state": result.get("state"),
        }
