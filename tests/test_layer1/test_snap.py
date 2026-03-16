"""Tests for 8-bar snapping pass."""

import numpy as np

from scue.layer1.detectors.snap import (
    snap_to_8bar_grid,
    _snap_to_nearest_downbeat,
    _count_bars,
    _nearest_standard_length,
)


class TestSnapHelpers:
    """Tests for snap helper functions."""

    def test_snap_to_nearest_downbeat(self) -> None:
        downbeats = np.array([0.0, 1.875, 3.75, 5.625, 7.5])
        # Should snap 2.0 to 1.875 (within tolerance)
        assert _snap_to_nearest_downbeat(2.0, downbeats, max_snap_sec=0.5) == 1.875

    def test_snap_no_downbeat_in_range(self) -> None:
        downbeats = np.array([0.0, 10.0, 20.0])
        # 5.0 is too far from any downbeat with small tolerance
        assert _snap_to_nearest_downbeat(5.0, downbeats, max_snap_sec=0.5) == 5.0

    def test_snap_empty_downbeats(self) -> None:
        assert _snap_to_nearest_downbeat(5.0, np.array([]), max_snap_sec=1.0) == 5.0

    def test_count_bars(self) -> None:
        downbeats = np.array([0.0, 1.875, 3.75, 5.625, 7.5, 9.375])
        assert _count_bars(0.0, 7.5, downbeats) == 4
        # 9.5 includes the downbeat at 9.375, so 6 downbeats total
        assert _count_bars(0.0, 9.5, downbeats) == 6

    def test_nearest_standard_length(self) -> None:
        assert _nearest_standard_length(7) == 8
        assert _nearest_standard_length(8) == 8
        assert _nearest_standard_length(9) == 8
        assert _nearest_standard_length(12) == 8  # equidistant to 8 and 16, picks 8
        assert _nearest_standard_length(15) == 16
        assert _nearest_standard_length(16) == 16
        assert _nearest_standard_length(30) == 32
        assert _nearest_standard_length(3) == 4


class TestSnapToGrid:
    """Tests for the full 8-bar snapping pass."""

    def _make_downbeats(self, bpm: float, n_bars: int) -> list[float]:
        """Generate evenly-spaced downbeat timestamps.

        Generates n_bars + 1 downbeats (one at the start of each bar,
        plus one at the very end to mark the final boundary).
        """
        bar_duration = 60.0 / bpm * 4
        return [i * bar_duration for i in range(n_bars + 1)]

    def test_snap_perfect_8bar(self) -> None:
        """Sections already on 8-bar boundaries should pass through."""
        bpm = 128.0
        bar_dur = 60.0 / bpm * 4  # 1.875s per bar
        downbeats = self._make_downbeats(bpm, 32)

        raw = [
            {"label": "intro", "start": 0.0, "end": 8 * bar_dur,
             "original_label": "intro", "confidence": 0.9},
            {"label": "drop", "start": 8 * bar_dur, "end": 24 * bar_dur,
             "original_label": "chorus", "confidence": 0.8},
            {"label": "outro", "start": 24 * bar_dur, "end": 32 * bar_dur,
             "original_label": "outro", "confidence": 0.9},
        ]

        result = snap_to_8bar_grid(raw, downbeats, bpm)
        assert len(result.sections) == 3
        # All sections should be regular (8-bar aligned)
        for s in result.sections:
            assert not s.irregular_phrase, f"{s.label}: {s.bar_count} bars flagged as irregular"

    def test_snap_irregular_flagged(self) -> None:
        """Sections not on 8-bar multiples should be flagged."""
        bpm = 128.0
        bar_dur = 60.0 / bpm * 4
        downbeats = self._make_downbeats(bpm, 20)

        # 6-bar section is irregular
        raw = [
            {"label": "intro", "start": 0.0, "end": 6 * bar_dur,
             "original_label": "intro", "confidence": 0.9},
            {"label": "drop", "start": 6 * bar_dur, "end": 20 * bar_dur,
             "original_label": "chorus", "confidence": 0.8},
        ]

        result = snap_to_8bar_grid(raw, downbeats, bpm)
        # At least one section should be irregular
        irregular_count = sum(1 for s in result.sections if s.irregular_phrase)
        assert irregular_count >= 1

    def test_snap_no_downbeats(self) -> None:
        """Should handle missing downbeats gracefully."""
        raw = [
            {"label": "intro", "start": 0.0, "end": 16.0,
             "original_label": "intro", "confidence": 0.5},
        ]
        result = snap_to_8bar_grid(raw, [], 128.0)
        assert len(result.sections) == 1
        assert result.snap_report[0].startswith("No downbeats")

    def test_snap_preserves_labels(self) -> None:
        """Snap should preserve original labels."""
        bpm = 128.0
        bar_dur = 60.0 / bpm * 4
        downbeats = self._make_downbeats(bpm, 16)

        raw = [
            {"label": "build", "start": 0.0, "end": 8 * bar_dur,
             "original_label": "verse", "confidence": 0.7},
            {"label": "drop", "start": 8 * bar_dur, "end": 16 * bar_dur,
             "original_label": "chorus", "confidence": 0.8},
        ]

        result = snap_to_8bar_grid(raw, downbeats, bpm)
        labels = [s.label for s in result.sections]
        assert "build" in labels
        assert "drop" in labels
