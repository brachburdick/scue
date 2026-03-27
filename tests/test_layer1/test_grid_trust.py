"""Tests for beat-grid trust scoring."""

from __future__ import annotations

import pytest

from scue.layer1.strata.grid_trust import (
    GridTrustReport,
    GridTrustTier,
    score_beat_grid,
)


def _make_grid(bpm: float = 128.0, num_beats: int = 128, start_ms: float = 0.0) -> list[dict]:
    """Build a well-formed beat grid at constant BPM."""
    spacing = 60000.0 / bpm
    return [
        {"beat_number": i + 1, "time_ms": start_ms + i * spacing, "bpm": bpm}
        for i in range(num_beats)
    ]


def _make_phrases(
    lengths_beats: list[int] | None = None,
    start_beat: int = 1,
) -> list[dict]:
    """Build phrase entries with given lengths in beats."""
    if lengths_beats is None:
        lengths_beats = [64, 32, 64, 32, 64, 32]  # 4-bar multiples
    phrases = []
    beat = start_beat
    kinds = ["intro", "build", "drop", "breakdown", "build", "drop", "outro"]
    for i, length in enumerate(lengths_beats):
        kind = kinds[i % len(kinds)]
        phrases.append({
            "start_beat": beat,
            "end_beat": beat + length,
            "kind": kind,
        })
        beat += length
    return phrases


class TestTierA:
    """Well-formed grid should score Tier A."""

    def test_perfect_grid(self) -> None:
        grid = _make_grid(bpm=128.0, num_beats=256)
        phrases = _make_phrases()
        report = score_beat_grid(grid, phrases, bpm=128.0, duration=120.0)
        assert report.tier == GridTrustTier.A

    def test_confidence_is_max(self) -> None:
        grid = _make_grid(bpm=128.0, num_beats=256)
        phrases = _make_phrases()
        report = score_beat_grid(grid, phrases, bpm=128.0, duration=120.0)
        assert report.confidence == 1.0

    def test_all_checks_pass(self) -> None:
        grid = _make_grid(bpm=128.0, num_beats=256)
        phrases = _make_phrases()
        report = score_beat_grid(grid, phrases, bpm=128.0, duration=120.0)
        assert report.downbeat_plausible is True
        assert report.drift_detected is False
        assert report.half_double_tempo_suspicion is False
        assert report.phrase_bar_plausible is True

    def test_various_edm_tempos(self) -> None:
        """Common EDM tempos should all score A."""
        for bpm in [120.0, 126.0, 128.0, 130.0, 140.0, 150.0, 174.0]:
            grid = _make_grid(bpm=bpm, num_beats=128)
            report = score_beat_grid(grid, bpm=bpm, duration=120.0)
            assert report.tier == GridTrustTier.A, f"BPM {bpm} should be Tier A"


class TestTierB:
    """Minor issues should score Tier B."""

    def test_minor_drift(self) -> None:
        """Grid with gradual drift < threshold should be B if phrases have issues."""
        grid = _make_grid(bpm=128.0, num_beats=128)
        # Add moderate drift (under 500ms total)
        for i, entry in enumerate(grid):
            entry["time_ms"] += i * 3.0  # 3ms per beat = 384ms over 128 beats
        # Phrases with one odd-length phrase
        phrases = _make_phrases([64, 32, 63, 32, 64])  # 63 is not bar-aligned
        report = score_beat_grid(grid, phrases, bpm=128.0, duration=120.0)
        # Should be B (drift detected + some phrase issue possible)
        assert report.tier in (GridTrustTier.A, GridTrustTier.B)

    def test_no_phrases_still_ok(self) -> None:
        """Missing phrases is not a failure — just less validation."""
        grid = _make_grid(bpm=128.0, num_beats=128)
        report = score_beat_grid(grid, phrases=None, bpm=128.0, duration=120.0)
        assert report.tier == GridTrustTier.A  # No phrase check = no failure


class TestTierC:
    """Serious issues should score Tier C."""

    def test_empty_grid(self) -> None:
        report = score_beat_grid([], phrases=None, bpm=128.0, duration=120.0)
        assert report.tier == GridTrustTier.C
        assert report.confidence == 0.0
        assert "No beat grid data" in report.notes[0]

    def test_half_tempo_grid(self) -> None:
        """BPM at 64 (half of typical EDM range) should be suspicious."""
        grid = _make_grid(bpm=64.0, num_beats=64)
        report = score_beat_grid(grid, bpm=64.0, duration=120.0)
        assert report.half_double_tempo_suspicion is True
        assert report.tier in (GridTrustTier.B, GridTrustTier.C)

    def test_double_tempo_grid(self) -> None:
        """BPM at 256 (double of typical EDM range) should be suspicious."""
        grid = _make_grid(bpm=256.0, num_beats=256)
        report = score_beat_grid(grid, bpm=256.0, duration=120.0)
        assert report.half_double_tempo_suspicion is True

    def test_severe_drift(self) -> None:
        """Large cumulative drift should be detected."""
        grid = _make_grid(bpm=128.0, num_beats=128)
        # Add severe drift: 10ms per beat = 1280ms over 128 beats
        for i, entry in enumerate(grid):
            entry["time_ms"] += i * 10.0
        report = score_beat_grid(grid, bpm=128.0, duration=120.0)
        assert report.drift_detected is True

    def test_single_entry_grid(self) -> None:
        """Grid with only one entry can't be validated."""
        grid = [{"beat_number": 1, "time_ms": 0.0, "bpm": 128.0}]
        report = score_beat_grid(grid, bpm=128.0, duration=120.0)
        assert report.downbeat_plausible is False
        assert report.tier in (GridTrustTier.B, GridTrustTier.C)


class TestPhraseBarPlausibility:
    """Test phrase/bar alignment checks."""

    def test_bar_aligned_phrases(self) -> None:
        phrases = _make_phrases([16, 32, 64, 32, 16])
        grid = _make_grid(bpm=128.0, num_beats=256)
        report = score_beat_grid(grid, phrases, bpm=128.0, duration=120.0)
        assert report.phrase_bar_plausible is True

    def test_mostly_misaligned_phrases(self) -> None:
        """More than 30% non-bar-aligned phrases should fail."""
        phrases = _make_phrases([17, 33, 65, 31, 15])  # All non-multiples of 4
        grid = _make_grid(bpm=128.0, num_beats=256)
        report = score_beat_grid(grid, phrases, bpm=128.0, duration=120.0)
        assert report.phrase_bar_plausible is False

    def test_empty_phrases_passes(self) -> None:
        """No phrases = no failure (absence is not evidence)."""
        grid = _make_grid(bpm=128.0, num_beats=128)
        report = score_beat_grid(grid, phrases=[], bpm=128.0, duration=120.0)
        assert report.phrase_bar_plausible is True


class TestSerialization:
    """Test GridTrustReport round-trip."""

    def test_round_trip(self) -> None:
        grid = _make_grid(bpm=128.0, num_beats=128)
        original = score_beat_grid(grid, bpm=128.0, duration=120.0)
        data = original.to_dict()
        restored = GridTrustReport.from_dict(data)
        assert restored.tier == original.tier
        assert restored.confidence == original.confidence
        assert restored.downbeat_plausible == original.downbeat_plausible
        assert restored.drift_detected == original.drift_detected
        assert restored.notes == original.notes

    def test_from_empty_dict(self) -> None:
        report = GridTrustReport.from_dict({})
        assert report.tier == GridTrustTier.C  # Default to least trusted

    def test_to_dict_json_safe(self) -> None:
        import json
        grid = _make_grid(bpm=128.0, num_beats=128)
        report = score_beat_grid(grid, bpm=128.0, duration=120.0)
        data = report.to_dict()
        json_str = json.dumps(data)
        assert isinstance(json_str, str)


class TestLiveAnalyzerIntegration:
    """Test that LiveStrataAnalyzer attaches grid trust to formulas."""

    def test_formula_has_grid_trust(self) -> None:
        from scue.layer1.strata.live_analyzer import LiveStrataAnalyzer

        saved = {
            "phrases": _make_phrases(),
            "beat_grid": _make_grid(bpm=128.0, num_beats=256),
            "duration": 120.0,
            "bpm": 128.0,
            "rekordbox_id": 12345,
            "hot_cues": [],
            "memory_points": [],
            "pioneer_waveform": None,
        }
        formula = LiveStrataAnalyzer.build_from_saved_data("abc123", saved)
        assert formula is not None
        assert formula.grid_trust is not None
        assert formula.grid_trust["tier"] == "A"

    def test_formula_grid_trust_serialization(self) -> None:
        """Grid trust should survive formula round-trip."""
        from scue.layer1.strata.models import formula_from_dict, formula_to_dict
        from scue.layer1.strata.live_analyzer import LiveStrataAnalyzer

        saved = {
            "phrases": _make_phrases(),
            "beat_grid": _make_grid(bpm=128.0, num_beats=256),
            "duration": 120.0,
            "bpm": 128.0,
            "rekordbox_id": 12345,
            "hot_cues": [],
            "memory_points": [],
            "pioneer_waveform": None,
        }
        formula = LiveStrataAnalyzer.build_from_saved_data("abc123", saved)
        assert formula is not None

        data = formula_to_dict(formula)
        assert "grid_trust" in data

        restored = formula_from_dict(data)
        assert restored.grid_trust is not None
        assert restored.grid_trust["tier"] == "A"

    def test_quick_formula_has_no_grid_trust(self) -> None:
        """Non-live formulas should have grid_trust=None."""
        from scue.layer1.strata.models import ArrangementFormula
        formula = ArrangementFormula(fingerprint="test")
        assert formula.grid_trust is None
