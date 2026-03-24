"""Tests for the Strata standard tier analysis engine.

Covers:
- StemSeparator caching and demucs availability check
- Per-stem analysis with synthetic audio
- Engine routing to the correct tier method
- Cross-stem transition detection
- Transition merging
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from scue.layer1.models import Section
from scue.layer1.strata.models import (
    ActivitySpan,
    ArrangementTransition,
    StemAnalysis,
    StemType,
    TransitionType,
)


def _can_import(module: str) -> bool:
    """Check if a module can be imported."""
    try:
        __import__(module)
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# StemSeparator tests
# ---------------------------------------------------------------------------


class TestStemSeparator:
    """Tests for the stem separation wrapper."""

    def test_stems_exist_false_when_dir_missing(self, tmp_path: Path) -> None:
        from scue.layer1.strata.separation import StemSeparator

        sep = StemSeparator(strata_dir=tmp_path)
        assert sep.stems_exist("abc123") is False

    def test_stems_exist_false_when_partial(self, tmp_path: Path) -> None:
        from scue.layer1.strata.separation import StemSeparator

        sep = StemSeparator(strata_dir=tmp_path)
        stems_dir = tmp_path / "abc123" / "stems"
        stems_dir.mkdir(parents=True)
        (stems_dir / "drums.wav").write_bytes(b"fake")
        (stems_dir / "bass.wav").write_bytes(b"fake")
        # Missing vocals.wav and other.wav
        assert sep.stems_exist("abc123") is False

    def test_stems_exist_true_when_all_present(self, tmp_path: Path) -> None:
        from scue.layer1.strata.separation import StemSeparator

        sep = StemSeparator(strata_dir=tmp_path)
        stems_dir = tmp_path / "abc123" / "stems"
        stems_dir.mkdir(parents=True)
        for stem in StemType:
            (stems_dir / f"{stem.value}.wav").write_bytes(b"fake")
        assert sep.stems_exist("abc123") is True

    def test_get_stem_paths(self, tmp_path: Path) -> None:
        from scue.layer1.strata.separation import StemSeparator

        sep = StemSeparator(strata_dir=tmp_path)
        paths = sep.get_stem_paths("abc123")
        assert len(paths) == 4
        assert StemType.DRUMS in paths
        assert paths[StemType.DRUMS] == tmp_path / "abc123" / "stems" / "drums.wav"

    def test_separate_returns_cached_when_exists(self, tmp_path: Path) -> None:
        from scue.layer1.strata.separation import StemSeparator

        sep = StemSeparator(strata_dir=tmp_path)
        # Pre-create stems
        stems_dir = tmp_path / "abc123" / "stems"
        stems_dir.mkdir(parents=True)
        for stem in StemType:
            (stems_dir / f"{stem.value}.wav").write_bytes(b"fake")

        # Should return cached paths without touching demucs
        result = sep.separate(Path("/nonexistent.wav"), "abc123")
        assert len(result) == 4

    def test_separate_raises_when_demucs_unavailable(self, tmp_path: Path) -> None:
        from scue.layer1.strata.separation import StemSeparator

        sep = StemSeparator(strata_dir=tmp_path)
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake")

        with patch("scue.layer1.strata.separation.is_demucs_available", return_value=False):
            with pytest.raises(RuntimeError, match="demucs"):
                sep.separate(audio, "abc123")

    def test_separate_raises_when_audio_missing(self, tmp_path: Path) -> None:
        from scue.layer1.strata.separation import StemSeparator

        sep = StemSeparator(strata_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            sep.separate(Path("/nonexistent.wav"), "abc123")

    def test_is_demucs_available(self) -> None:
        from scue.layer1.strata.separation import is_demucs_available

        # Just verify it returns a bool without crashing
        result = is_demucs_available()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Per-stem analysis tests
# ---------------------------------------------------------------------------


class TestPerStemAnalysis:
    """Tests for per-stem analysis with synthetic audio."""

    def _make_synthetic_stem(self, tmp_path: Path, name: str, freq: float = 440.0) -> Path:
        """Create a synthetic WAV file for testing."""
        import soundfile as sf

        sr = 22050
        duration = 10.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        # Sine wave with amplitude envelope (active then silent)
        signal = np.sin(2 * np.pi * freq * t).astype(np.float32)
        # Fade to silence after 7 seconds
        signal[int(sr * 7):] *= 0.0

        path = tmp_path / f"{name}.wav"
        sf.write(str(path), signal, sr)
        return path

    def test_compute_stem_activity(self) -> None:
        from scue.layer1.strata.energy import EnergyAnalysis
        from scue.layer1.strata.per_stem import _compute_stem_activity

        # Simulate 10 bars of energy: high for first 7, silent for last 3
        bar_energies = [0.8, 0.9, 0.7, 0.85, 0.9, 0.8, 0.7, 0.0, 0.0, 0.0]
        downbeats = [i * 2.0 for i in range(11)]  # 2s per bar
        energy = EnergyAnalysis(bar_energies_total=bar_energies)

        spans = _compute_stem_activity(energy, downbeats, 20.0, StemType.DRUMS)
        assert len(spans) >= 1
        # First span should cover the active bars
        assert spans[0].bar_start == 0
        assert spans[0].bar_end == 7

    def test_normalize_energy_curve(self) -> None:
        from scue.layer1.strata.per_stem import _normalize_energy_curve

        curve = _normalize_energy_curve([0.0, 0.5, 1.0, 0.25])
        assert curve == [0.0, 0.5, 1.0, 0.25]

        # Empty input
        assert _normalize_energy_curve([]) == []

        # All zeros
        assert _normalize_energy_curve([0.0, 0.0]) == [0.0, 0.0]

    def test_time_to_bar(self) -> None:
        from scue.layer1.strata.per_stem import _time_to_bar

        downbeats = [0.0, 2.0, 4.0, 6.0, 8.0]
        assert _time_to_bar(0.0, downbeats) == 0
        assert _time_to_bar(3.0, downbeats) == 1
        assert _time_to_bar(7.5, downbeats) == 3
        assert _time_to_bar(0.0, []) is None

    @pytest.mark.skipif(
        not _can_import("librosa"),
        reason="librosa not installed",
    )
    def test_analyze_stem_drums(self, tmp_path: Path) -> None:
        from scue.layer1.strata.per_stem import analyze_stem

        stem_path = self._make_synthetic_stem(tmp_path, "drums", freq=100.0)
        downbeats = [i * 2.0 for i in range(6)]  # 5 bars
        beats = [i * 0.5 for i in range(21)]

        result = analyze_stem(
            stem_path=stem_path,
            stem_type=StemType.DRUMS,
            downbeats=downbeats,
            beats=beats,
            duration=10.0,
            sections=[
                Section(label="intro", start=0.0, end=4.0),
                Section(label="drop", start=4.0, end=10.0),
            ],
        )

        assert result.stem_type == "drums"
        assert result.layer_role == "rhythm"
        assert len(result.energy_curve) > 0
        assert len(result.activity) > 0

    @pytest.mark.skipif(
        not _can_import("librosa"),
        reason="librosa not installed",
    )
    def test_analyze_stem_bass(self, tmp_path: Path) -> None:
        from scue.layer1.strata.per_stem import analyze_stem

        stem_path = self._make_synthetic_stem(tmp_path, "bass", freq=60.0)
        downbeats = [i * 2.0 for i in range(6)]
        beats = [i * 0.5 for i in range(21)]

        result = analyze_stem(
            stem_path=stem_path,
            stem_type=StemType.BASS,
            downbeats=downbeats,
            beats=beats,
            duration=10.0,
            sections=[
                Section(label="intro", start=0.0, end=10.0),
            ],
        )

        assert result.stem_type == "bass"
        assert result.layer_role == "bassline"
        assert len(result.energy_curve) > 0


# ---------------------------------------------------------------------------
# Cross-stem transition detection tests
# ---------------------------------------------------------------------------


class TestCrossStemTransitions:
    """Tests for cross-stem transition detection."""

    def test_detect_layer_enter_exit(self) -> None:
        from scue.layer1.strata.per_stem import detect_cross_stem_transitions

        stems = [
            StemAnalysis(
                stem_type="drums",
                activity=[
                    ActivitySpan(start=0.0, end=60.0, bar_start=0, bar_end=30, energy=0.8),
                ],
            ),
            StemAnalysis(
                stem_type="bass",
                activity=[
                    ActivitySpan(start=10.0, end=50.0, bar_start=5, bar_end=25, energy=0.7),
                ],
            ),
        ]
        sections = [
            Section(label="intro", start=0.0, end=20.0),
            Section(label="drop", start=20.0, end=60.0),
        ]

        transitions = detect_cross_stem_transitions(stems, [], sections)

        # Should have 4 transitions: 2 enters + 2 exits
        assert len(transitions) == 4

        enters = [t for t in transitions if t.type == TransitionType.LAYER_ENTER]
        exits = [t for t in transitions if t.type == TransitionType.LAYER_EXIT]
        assert len(enters) == 2
        assert len(exits) == 2

        # Check bass enter
        bass_enter = [t for t in enters if "bass" in t.layers_affected]
        assert len(bass_enter) == 1
        assert bass_enter[0].timestamp == 10.0

    def test_empty_stems(self) -> None:
        from scue.layer1.strata.per_stem import detect_cross_stem_transitions

        transitions = detect_cross_stem_transitions([], [], [])
        assert transitions == []


# ---------------------------------------------------------------------------
# Transition merging tests
# ---------------------------------------------------------------------------


class TestTransitionMerging:
    """Tests for merging cross-stem and energy-based transitions."""

    def test_merge_no_overlap(self) -> None:
        from scue.layer1.strata.engine import _merge_transitions

        cross = [
            ArrangementTransition(
                type=TransitionType.LAYER_ENTER, timestamp=10.0,
            ),
        ]
        energy = [
            ArrangementTransition(
                type=TransitionType.ENERGY_SHIFT, timestamp=30.0,
            ),
        ]

        merged = _merge_transitions(cross, energy)
        assert len(merged) == 2

    def test_merge_overlap_drops_energy(self) -> None:
        from scue.layer1.strata.engine import _merge_transitions

        cross = [
            ArrangementTransition(
                type=TransitionType.LAYER_ENTER, timestamp=10.0,
            ),
        ]
        energy = [
            ArrangementTransition(
                type=TransitionType.ENERGY_SHIFT, timestamp=10.5,
            ),
        ]

        merged = _merge_transitions(cross, energy, merge_window=2.0)
        # Energy transition at 10.5 is within 2.0s of cross at 10.0
        assert len(merged) == 1
        assert merged[0].type == TransitionType.LAYER_ENTER


# ---------------------------------------------------------------------------
# Engine routing tests
# ---------------------------------------------------------------------------


class TestEngineRouting:
    """Tests for engine tier routing."""

    def test_analyze_routes_to_quick(self, tmp_path: Path) -> None:
        from scue.layer1.strata.engine import StrataEngine
        from scue.layer1.strata.storage import StrataStore

        store = StrataStore(tmp_path / "strata")
        engine = StrataEngine(tracks_dir=tmp_path / "tracks", strata_store=store)

        with patch.object(engine, "analyze_quick") as mock_quick:
            mock_quick.return_value = MagicMock()
            engine.analyze("abc123", ["quick"])
            mock_quick.assert_called_once_with("abc123", analysis_version=None)

    def test_analyze_routes_to_standard(self, tmp_path: Path) -> None:
        from scue.layer1.strata.engine import StrataEngine
        from scue.layer1.strata.storage import StrataStore

        store = StrataStore(tmp_path / "strata")
        engine = StrataEngine(tracks_dir=tmp_path / "tracks", strata_store=store)

        with patch.object(engine, "analyze_standard") as mock_standard:
            mock_standard.return_value = MagicMock()
            engine.analyze("abc123", ["standard"])
            mock_standard.assert_called_once_with("abc123", analysis_version=None)

    def test_analyze_routes_both(self, tmp_path: Path) -> None:
        from scue.layer1.strata.engine import StrataEngine
        from scue.layer1.strata.storage import StrataStore

        store = StrataStore(tmp_path / "strata")
        engine = StrataEngine(tracks_dir=tmp_path / "tracks", strata_store=store)

        with patch.object(engine, "analyze_quick") as mock_quick, \
             patch.object(engine, "analyze_standard") as mock_standard:
            mock_quick.return_value = MagicMock()
            mock_standard.return_value = MagicMock()
            result = engine.analyze("abc123", ["quick", "standard"])
            mock_quick.assert_called_once()
            mock_standard.assert_called_once()
            assert "quick" in result
            assert "standard" in result

    def test_standard_tier_requires_demucs(self, tmp_path: Path) -> None:
        from scue.layer1.strata.engine import StrataEngine
        from scue.layer1.strata.storage import StrataStore

        store = StrataStore(tmp_path / "strata")
        engine = StrataEngine(tracks_dir=tmp_path / "tracks", strata_store=store)

        with patch("scue.layer1.strata.separation.is_demucs_available", return_value=False):
            with pytest.raises(RuntimeError, match="demucs"):
                engine.analyze_standard("abc123")


