"""Music theory sanity checks for the pure-Python generator layer."""

from __future__ import annotations

from fl_studio_mcp.tools.generators import (
    CHORDS, COMMON_PROGRESSIONS, DRUM_PATTERNS, SCALES,
    _chord_midi, _parse_root,
)


def test_parse_root():
    assert _parse_root("C4") == 60
    assert _parse_root("A4") == 69
    assert _parse_root("C5") == 72
    assert _parse_root("F#3") == 54


def test_c_major_triad():
    assert _chord_midi(60, "maj") == [60, 64, 67]


def test_c_min7():
    assert _chord_midi(60, "min7") == [60, 63, 67, 70]


def test_c_maj_first_inversion():
    # C major, 1st inversion: E G C
    assert _chord_midi(60, "maj", inversion=1) == [64, 67, 72]


def test_all_scales_have_unique_intervals():
    for name, iv in SCALES.items():
        assert iv == sorted(iv), f"{name} not ascending"
        assert len(set(iv)) == len(iv), f"{name} has dupes"


def test_all_chords_start_at_root():
    for name, iv in CHORDS.items():
        assert iv[0] == 0, name


def test_all_progressions_use_valid_qualities():
    for name, prog in COMMON_PROGRESSIONS.items():
        for degree, quality in prog:
            assert quality in CHORDS, f"{name}: unknown quality {quality}"


def test_drum_patterns_are_16_steps():
    for name, grid in DRUM_PATTERNS.items():
        for drum, hits in grid.items():
            assert len(hits) == 16, f"{name}/{drum} has {len(hits)} steps"
            assert all(h in (0, 1) for h in hits), f"{name}/{drum} has non-bit value"
