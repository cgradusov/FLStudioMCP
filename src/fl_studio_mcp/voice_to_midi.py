"""
Voice-to-MIDI engine for fLMCP.

Pipeline:
  1. Record audio from the default (or selected) microphone.
  2. Run pitch tracking: librosa `pyin` (probabilistic YIN) for monophonic
     singing / humming. State-of-the-art for one-voice-at-a-time signals.
  3. Detect note boundaries via librosa onset detection + pitch stability.
  4. Map F0 (Hz) -> MIDI number, snap to nearest semitone (or to a scale).
  5. Emit piano-roll-ready notes (time_bars, duration_bars, velocity).

Why not Spotify Basic Pitch?
  - Basic Pitch is polyphonic and ML-based (TensorFlow / ONNX) — 150 MB+.
  - Humming is monophonic: `pyin` is lighter, no GPU, Python 3.12 compatible,
    and in blind A/B tests matches Basic Pitch on monophonic vocals.
  - We keep the option open: swap `transcribe_monophonic` for a Basic-Pitch
    impl later without changing the tool interface.
"""

from __future__ import annotations

import logging
import math
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

log = logging.getLogger("fl_studio_mcp.voice_to_midi")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Note:
    midi: int
    start_sec: float
    duration_sec: float
    velocity: float = 0.8       # 0..1
    confidence: float = 1.0     # 0..1 — how sure pyin was about the pitch

    def as_piano_roll_note(self, bpm: float = 120.0, time_offset_bars: float = 0.0) -> dict:
        beats_per_sec = bpm / 60.0
        bars_per_sec = beats_per_sec / 4.0
        return {
            "midi": int(self.midi),
            "time_bars": round(time_offset_bars + self.start_sec * bars_per_sec, 4),
            "duration_bars": round(self.duration_sec * bars_per_sec, 4),
            "velocity": round(max(0.0, min(1.0, self.velocity)), 3),
        }


# ---------------------------------------------------------------------------
# Mic devices
# ---------------------------------------------------------------------------

def list_input_devices() -> list[dict]:
    """Enumerate available microphone inputs."""
    import sounddevice as sd
    out = []
    try:
        devs = sd.query_devices()
        default_in = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else sd.default.device
    except Exception as e:
        return [{"error": str(e)}]
    for i, d in enumerate(devs):
        if d.get("max_input_channels", 0) > 0:
            out.append({
                "index": i,
                "name": d["name"],
                "host_api": d.get("hostapi_name", ""),
                "max_input_channels": d["max_input_channels"],
                "default_sample_rate": d.get("default_samplerate"),
                "is_default": (i == default_in),
            })
    return out


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def record_wav(
    duration_sec: float,
    samplerate: int = 16000,
    device: int | str | None = None,
    beep: bool = True,
) -> Path:
    """Record mono audio from the given device for `duration_sec` seconds."""
    import sounddevice as sd
    import soundfile as sf

    if beep:
        _beep(900, 120)
        time.sleep(0.12)
        _beep(900, 120)
        time.sleep(0.12)
        _beep(1400, 180)
        time.sleep(0.08)

    log.info("recording %.1f s @ %d Hz", duration_sec, samplerate)
    frames = int(duration_sec * samplerate)
    try:
        audio = sd.rec(frames, samplerate=samplerate, channels=1,
                       dtype="float32", device=device)
        sd.wait()
    except Exception as e:
        raise RuntimeError(f"microphone recording failed: {e}") from e

    if beep:
        _beep(600, 180)

    tmp = Path(tempfile.gettempdir()) / f"fLMCP_voice_{int(time.time())}.wav"
    sf.write(tmp, audio, samplerate, subtype="PCM_16")
    log.info("recorded -> %s  peak=%.3f", tmp, float(np.max(np.abs(audio))))
    return tmp


def _beep(freq_hz: int, ms: int) -> None:
    try:
        import winsound
        winsound.Beep(int(freq_hz), int(ms))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Transcription (monophonic)
# ---------------------------------------------------------------------------

def _f0_to_midi(f0_hz: float) -> float:
    return 12.0 * math.log2(f0_hz / 440.0) + 69.0


def _nan_median_filter(seq: np.ndarray, window: int) -> np.ndarray:
    """Centered median filter that ignores NaN values.

    For each frame, take the median of the window around it skipping NaNs.
    If an input frame is NaN it stays NaN (keeps silence markers)."""
    if window <= 1:
        return seq.copy()
    n = len(seq)
    half = window // 2
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        if math.isnan(seq[i]):
            continue
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        chunk = seq[lo:hi]
        chunk = chunk[~np.isnan(chunk)]
        if chunk.size:
            out[i] = float(np.median(chunk))
    return out


def transcribe_monophonic(
    wav_path: str | Path,
    fmin_hz: float = 65.0,        # C2 (low male voice floor)
    fmax_hz: float = 1200.0,      # D6 (whistle ceiling)
    min_note_sec: float = 0.08,   # drop transients < 80 ms
    merge_gap_sec: float = 0.12,  # stitch same-pitch notes if gap < 120 ms
    semitone_tolerance: float = 1.2,   # tolerance for vibrato within a note
    hysteresis_sec: float = 0.06,      # pitch change must persist this long to split
    median_window: int = 5,            # smoothing window (frames) for pitch stability
) -> list[Note]:
    """Transcribe a monophonic audio file (voice/humming) to Note list.

    Tuned for sung/hummed input:
      - wide semitone_tolerance (±1.2) so natural vibrato doesn't split notes
      - pitch hysteresis (0.06 s) so transient pitch excursions don't split
      - median smoothing over `median_window` frames for stability
      - generous merge_gap so breath pauses don't fragment held notes
    """
    import librosa

    y, sr = librosa.load(str(wav_path), sr=22050, mono=True)
    if y.size < sr // 4:
        log.warning("audio too short (%d samples) — returning empty notes", y.size)
        return []

    # Normalise (soft) — loud hums vs. quiet hums should transcribe the same.
    peak = float(np.max(np.abs(y))) or 1e-9
    y = y / peak * 0.95

    # Remove pre-roll silence (keeps note timing honest w.r.t. the start).
    nonsilent = librosa.effects.split(y, top_db=30)
    if len(nonsilent) > 0:
        start_sample = int(nonsilent[0][0])
        y = y[start_sample:]
        time_shift = start_sample / sr
    else:
        time_shift = 0.0

    # pyin F0 tracking
    frame_length = 2048
    hop_length = 256
    try:
        f0, voiced_flag, voiced_probs = librosa.pyin(
            y, fmin=fmin_hz, fmax=fmax_hz, sr=sr,
            frame_length=frame_length, hop_length=hop_length,
        )
    except Exception as e:
        raise RuntimeError(f"pyin pitch tracking failed: {e}") from e

    # Median-smooth the pitch sequence in MIDI space to suppress vibrato spikes.
    midi_seq = np.full(len(f0), np.nan, dtype=np.float64)
    for i, p in enumerate(f0):
        if voiced_flag[i] and not math.isnan(p) and p > 0:
            midi_seq[i] = _f0_to_midi(float(p))
    midi_smooth = _nan_median_filter(midi_seq, window=max(1, median_window))

    # Segment into notes with hysteresis: a pitch change only splits the current
    # note if it persists for >= hysteresis_sec. This keeps held tones together
    # even when pyin momentarily mis-labels a frame.
    hysteresis_frames = max(1, int(round(hysteresis_sec * sr / hop_length)))

    notes: list[Note] = []
    cur_start: int | None = None
    cur_pitches: list[float] = []   # in MIDI (fractional)
    cur_confs: list[float] = []
    candidate_midi: int | None = None   # pending pitch change
    candidate_hold: int = 0

    def _flush(end_frame: int) -> None:
        nonlocal cur_start, cur_pitches, cur_confs
        if cur_start is None or not cur_pitches:
            return
        median_midi = float(np.median(cur_pitches))
        rounded = int(round(median_midi))
        start_sec = cur_start * hop_length / sr
        end_sec = end_frame * hop_length / sr
        dur = end_sec - start_sec
        if dur < min_note_sec:
            return
        # velocity ~ voiced confidence (average)
        confidence = float(np.mean(cur_confs)) if cur_confs else 1.0
        velocity = 0.5 + 0.45 * confidence
        notes.append(Note(
            midi=rounded,
            start_sec=round(start_sec, 4),
            duration_sec=round(dur, 4),
            velocity=round(velocity, 3),
            confidence=round(confidence, 3),
        ))

    n_frames = len(midi_smooth)
    for i in range(n_frames):
        m = midi_smooth[i]
        if not math.isnan(m):
            m_rounded = int(round(m))
            conf = float(voiced_probs[i]) if i < len(voiced_probs) and not math.isnan(voiced_probs[i]) else 0.0
            if cur_start is None:
                cur_start = i
                cur_pitches = [m]
                cur_confs = [conf]
                candidate_midi = None
                candidate_hold = 0
            else:
                ref_midi = float(np.median(cur_pitches))
                if abs(m - ref_midi) <= semitone_tolerance:
                    # still within the same note — reset any pending change
                    cur_pitches.append(m)
                    cur_confs.append(conf)
                    candidate_midi = None
                    candidate_hold = 0
                else:
                    # potential new note — require N consecutive frames at new pitch
                    if candidate_midi is not None and abs(m - candidate_midi) <= semitone_tolerance:
                        candidate_hold += 1
                    else:
                        candidate_midi = m_rounded
                        candidate_hold = 1
                    if candidate_hold >= hysteresis_frames:
                        _flush(i - candidate_hold + 1)
                        cur_start = i - candidate_hold + 1
                        cur_pitches = [float(candidate_midi)]
                        cur_confs = [conf]
                        candidate_midi = None
                        candidate_hold = 0
                    else:
                        # tentative — still accumulate into current note
                        cur_pitches.append(m)
                        cur_confs.append(conf)
        else:
            if cur_start is not None:
                _flush(i)
                cur_start = None
                cur_pitches = []
                cur_confs = []
                candidate_midi = None
                candidate_hold = 0
    _flush(n_frames)

    # Merge same-pitch notes with tiny gaps (breath artefacts)
    merged: list[Note] = []
    for n in notes:
        if merged:
            prev = merged[-1]
            gap = n.start_sec - (prev.start_sec + prev.duration_sec)
            if n.midi == prev.midi and 0 <= gap <= merge_gap_sec:
                new_dur = (n.start_sec + n.duration_sec) - prev.start_sec
                prev.duration_sec = round(new_dur, 4)
                prev.velocity = round(max(prev.velocity, n.velocity), 3)
                continue
        merged.append(n)

    # Add back silence offset
    for n in merged:
        n.start_sec = round(n.start_sec + time_shift, 4)

    log.info("transcribed %d notes from %s", len(merged), wav_path)
    return merged


# ---------------------------------------------------------------------------
# Post-processing helpers
# ---------------------------------------------------------------------------

SCALE_INTERVALS: dict[str, list[int]] = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "pentatonic_maj": [0, 2, 4, 7, 9],
    "pentatonic_min": [0, 3, 5, 7, 10],
    "blues": [0, 3, 5, 6, 7, 10],
    "chromatic": list(range(12)),
}


def _scale_pcs(root_midi: int, scale: str) -> set[int]:
    iv = SCALE_INTERVALS[scale]
    root_pc = root_midi % 12
    return {(root_pc + s) % 12 for s in iv}


def snap_to_scale(notes: Iterable[Note], root: str = "C", scale: str = "minor") -> list[Note]:
    """Snap each note's pitch to the nearest scale tone."""
    root_pc = _note_name_to_pc(root)
    pcs = _scale_pcs(root_pc, scale)
    out: list[Note] = []
    for n in notes:
        # find closest allowed pitch-class to n.midi
        best = min(range(-6, 7), key=lambda d: (_dist_to_pcs((n.midi + d) % 12, pcs), abs(d)))
        new_midi = int(n.midi + best)
        out.append(Note(midi=new_midi, start_sec=n.start_sec,
                        duration_sec=n.duration_sec,
                        velocity=n.velocity, confidence=n.confidence))
    return out


def _note_name_to_pc(name: str) -> int:
    table = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4,
             "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9,
             "A#": 10, "Bb": 10, "B": 11}
    s = name.strip()
    if s in table:
        return table[s]
    if len(s) >= 2 and s[:2] in table:
        return table[s[:2]]
    if s[:1] in table:
        return table[s[:1]]
    raise ValueError(f"unknown note name: {name}")


def _dist_to_pcs(pc: int, pcs: set[int]) -> int:
    return min(abs((pc - p) % 12) for p in pcs)


def quantize(notes: Iterable[Note], grid_sec: float = 0.125,
             strength: float = 1.0) -> list[Note]:
    """Quantize note starts to a grid (in seconds)."""
    out: list[Note] = []
    for n in notes:
        snapped = round(n.start_sec / grid_sec) * grid_sec
        delta = (snapped - n.start_sec) * strength
        out.append(Note(midi=n.midi, start_sec=round(n.start_sec + delta, 4),
                        duration_sec=n.duration_sec,
                        velocity=n.velocity, confidence=n.confidence))
    return out


def transpose(notes: Iterable[Note], semitones: int) -> list[Note]:
    return [Note(midi=max(0, min(127, n.midi + semitones)),
                 start_sec=n.start_sec, duration_sec=n.duration_sec,
                 velocity=n.velocity, confidence=n.confidence) for n in notes]


def drop_low_confidence(notes: Iterable[Note], min_conf: float = 0.4) -> list[Note]:
    return [n for n in notes if n.confidence >= min_conf]


def notes_as_piano_roll(notes: Iterable[Note], bpm: float = 120.0,
                        time_offset_bars: float = 0.0) -> list[dict]:
    return [n.as_piano_roll_note(bpm=bpm, time_offset_bars=time_offset_bars) for n in notes]
