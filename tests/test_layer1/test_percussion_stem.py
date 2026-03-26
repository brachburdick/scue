"""Tests for the stem-aware drum event detector (StemDrumDetector).

Uses synthetic audio signals to test multi-band onset detection,
snap-to-grid, pattern grouping, and multi-label classification.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


def _can_import(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


needs_librosa = pytest.mark.skipif(
    not _can_import("librosa"),
    reason="librosa not installed",
)
needs_scipy = pytest.mark.skipif(
    not _can_import("scipy"),
    reason="scipy not installed",
)


# ---------------------------------------------------------------------------
# Synthetic audio helpers
# ---------------------------------------------------------------------------

def _make_kick_impulse(sr: int = 22050, duration: float = 0.05) -> np.ndarray:
    """Create a synthetic kick drum: low-frequency decaying sine."""
    n = int(sr * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    # 80 Hz fundamental with exponential decay
    envelope = np.exp(-t * 40)
    return (np.sin(2 * np.pi * 80 * t) * envelope).astype(np.float32)


def _make_snare_impulse(sr: int = 22050, duration: float = 0.04) -> np.ndarray:
    """Create a synthetic snare: mid-frequency noise burst."""
    n = int(sr * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    envelope = np.exp(-t * 50)
    # Band-limited noise (200-5000 Hz character)
    noise = np.random.RandomState(42).randn(n).astype(np.float32)
    # Add a tonal body at 250 Hz
    tonal = np.sin(2 * np.pi * 250 * t).astype(np.float32) * 0.5
    return ((noise * 0.7 + tonal) * envelope).astype(np.float32)


def _make_hihat_impulse(sr: int = 22050, duration: float = 0.02) -> np.ndarray:
    """Create a synthetic hi-hat: high-frequency noise burst."""
    n = int(sr * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    envelope = np.exp(-t * 80)
    # High-frequency noise
    noise = np.random.RandomState(99).randn(n).astype(np.float32)
    # High-pass: multiply by high-freq sine to push energy up
    carrier = np.sin(2 * np.pi * 8000 * t).astype(np.float32)
    return (noise * carrier * envelope).astype(np.float32)


def _place_impulses(
    total_samples: int,
    impulse: np.ndarray,
    times: list[float],
    sr: int,
    amplitude: float = 1.0,
) -> np.ndarray:
    """Place impulses at specified times in a silent buffer."""
    signal = np.zeros(total_samples, dtype=np.float32)
    for t in times:
        start = int(t * sr)
        end = min(start + len(impulse), total_samples)
        n = end - start
        if n > 0:
            signal[start:end] += impulse[:n] * amplitude
    return signal


def _make_beatgrid(bpm: float, duration: float) -> tuple[list[float], list[float]]:
    """Create beat and downbeat lists for a given BPM and duration."""
    beat_dur = 60.0 / bpm
    beats = []
    t = 0.0
    while t < duration:
        beats.append(t)
        t += beat_dur

    bar_dur = beat_dur * 4
    downbeats = []
    t = 0.0
    while t < duration:
        downbeats.append(t)
        t += bar_dur

    return beats, downbeats


# ---------------------------------------------------------------------------
# Tests: StemDrumDetector
# ---------------------------------------------------------------------------

@needs_librosa
@needs_scipy
class TestStemDrumDetector:
    """Tests for multi-band stem drum detection."""

    def _get_detector(self):
        from scue.layer1.detectors.percussion_stem import StemDrumConfig, StemDrumDetector
        # Use default config for tests
        return StemDrumDetector(config=StemDrumConfig())

    def test_kick_detection(self) -> None:
        """Kick impulses at every beat should be detected as kicks."""
        sr = 22050
        bpm = 120.0
        duration = 8.0  # 4 bars
        beats, downbeats = _make_beatgrid(bpm, duration)
        total_samples = int(sr * duration)

        kick = _make_kick_impulse(sr)
        # Place kicks on every beat (4-on-the-floor)
        kick_times = beats[:len(beats) - 1]
        signal = _place_impulses(total_samples, kick, kick_times, sr, amplitude=1.0)

        from scue.layer1.models import Section
        sections = [Section(label="drop", start=0.0, end=duration)]

        detector = self._get_detector()
        patterns, events = detector.detect(signal, sr, beats, downbeats, sections)

        # Should have patterns
        assert len(patterns) > 0, "Expected at least one DrumPattern"

        # Should have kick events
        kick_events = [e for e in events if e.type == "kick"]
        assert len(kick_events) >= 4, f"Expected >=4 kick events, got {len(kick_events)}"

        # Kick events should be at beat positions (slots 0, 4, 8, 12)
        kick_slots = {e.beat_position for e in kick_events}
        assert kick_slots & {0, 4, 8, 12}, "Kick events should land on quarter-note slots"

    def test_snare_detection(self) -> None:
        """Snare impulses on beats 2 and 4 should be detected as snares."""
        sr = 22050
        bpm = 120.0
        duration = 8.0
        beats, downbeats = _make_beatgrid(bpm, duration)
        total_samples = int(sr * duration)

        snare = _make_snare_impulse(sr)
        # Place snares on beats 2 and 4 of each bar
        beat_dur = 60.0 / bpm
        snare_times = [db + beat_dur for db in downbeats[:-1]]  # beat 2
        snare_times += [db + 3 * beat_dur for db in downbeats[:-1]]  # beat 4
        snare_times.sort()

        signal = _place_impulses(total_samples, snare, snare_times, sr, amplitude=1.0)

        from scue.layer1.models import Section
        sections = [Section(label="drop", start=0.0, end=duration)]

        detector = self._get_detector()
        patterns, events = detector.detect(signal, sr, beats, downbeats, sections)

        # Should have snare events
        snare_events = [e for e in events if e.type == "snare"]
        assert len(snare_events) >= 2, f"Expected >=2 snare events, got {len(snare_events)}"

    def test_hihat_detection(self) -> None:
        """Hi-hat impulses at 8th-note positions should be detected."""
        sr = 22050
        bpm = 120.0
        duration = 8.0
        beats, downbeats = _make_beatgrid(bpm, duration)
        total_samples = int(sr * duration)

        hihat = _make_hihat_impulse(sr)
        # Place hi-hats on every 8th note
        beat_dur = 60.0 / bpm
        hihat_times = []
        for beat in beats[:-1]:
            hihat_times.append(beat)
            hihat_times.append(beat + beat_dur / 2)

        signal = _place_impulses(total_samples, hihat, hihat_times, sr, amplitude=0.5)

        from scue.layer1.models import Section
        sections = [Section(label="drop", start=0.0, end=duration)]

        detector = self._get_detector()
        patterns, events = detector.detect(signal, sr, beats, downbeats, sections)

        hihat_events = [e for e in events if e.type == "hihat"]
        assert len(hihat_events) >= 4, f"Expected >=4 hihat events, got {len(hihat_events)}"

    def test_simultaneous_kick_snare(self) -> None:
        """Overlaid kick+snare at the same time should detect both."""
        sr = 22050
        bpm = 120.0
        duration = 4.0  # 2 bars
        beats, downbeats = _make_beatgrid(bpm, duration)
        total_samples = int(sr * duration)

        kick = _make_kick_impulse(sr)
        snare = _make_snare_impulse(sr)

        # Place kick+snare simultaneously on beat 1 of each bar
        hit_times = downbeats[:-1]
        signal = _place_impulses(total_samples, kick, hit_times, sr, amplitude=1.0)
        signal += _place_impulses(total_samples, snare, hit_times, sr, amplitude=0.8)

        from scue.layer1.models import Section
        sections = [Section(label="drop", start=0.0, end=duration)]

        detector = self._get_detector()
        _, events = detector.detect(signal, sr, beats, downbeats, sections)

        kick_events = [e for e in events if e.type == "kick"]
        snare_events = [e for e in events if e.type == "snare"]

        # Both should be detected at overlapping timestamps
        assert len(kick_events) >= 1, "Should detect kicks in simultaneous hit"
        assert len(snare_events) >= 1, "Should detect snares in simultaneous hit"

    def test_empty_signal(self) -> None:
        """Silent input should produce no detections."""
        sr = 22050
        duration = 4.0
        beats, downbeats = _make_beatgrid(120.0, duration)
        signal = np.zeros(int(sr * duration), dtype=np.float32)

        from scue.layer1.models import Section
        sections = [Section(label="intro", start=0.0, end=duration)]

        detector = self._get_detector()
        patterns, events = detector.detect(signal, sr, beats, downbeats, sections)

        assert len(events) == 0, f"Expected no events on silent signal, got {len(events)}"

    def test_no_beats_no_crash(self) -> None:
        """Empty beats/downbeats should return empty results, not crash."""
        sr = 22050
        signal = np.random.randn(sr * 2).astype(np.float32) * 0.1

        detector = self._get_detector()
        patterns, events = detector.detect(signal, sr, [], [], [])
        assert patterns == []
        assert events == []

    def test_pattern_grouping(self) -> None:
        """4 identical bars should produce a single pattern spanning all 4."""
        sr = 22050
        bpm = 120.0
        duration = 8.0
        beats, downbeats = _make_beatgrid(bpm, duration)
        total_samples = int(sr * duration)

        kick = _make_kick_impulse(sr)
        # 4-on-the-floor for 4 bars
        signal = _place_impulses(total_samples, kick, beats[:16], sr, amplitude=1.0)

        from scue.layer1.models import Section
        sections = [Section(label="drop", start=0.0, end=duration)]

        detector = self._get_detector()
        patterns, _ = detector.detect(signal, sr, beats, downbeats, sections)

        assert len(patterns) >= 1
        # First pattern should span at least 4 bars (could be grouped as one)
        total_bars = sum(p.bar_end - p.bar_start for p in patterns)
        assert total_bars >= 4, f"Expected patterns spanning >=4 bars, got {total_bars}"

    def test_pattern_has_correct_fields(self) -> None:
        """DrumPattern objects should have all required fields."""
        sr = 22050
        bpm = 120.0
        duration = 8.0
        beats, downbeats = _make_beatgrid(bpm, duration)
        total_samples = int(sr * duration)

        kick = _make_kick_impulse(sr)
        signal = _place_impulses(total_samples, kick, beats[:16], sr, amplitude=1.0)

        from scue.layer1.models import Section
        sections = [Section(label="drop", start=0.0, end=duration)]

        detector = self._get_detector()
        patterns, _ = detector.detect(signal, sr, beats, downbeats, sections)

        assert len(patterns) >= 1
        p = patterns[0]
        assert hasattr(p, "bar_start")
        assert hasattr(p, "bar_end")
        assert hasattr(p, "kick")
        assert hasattr(p, "snare")
        assert hasattr(p, "clap")
        assert hasattr(p, "hihat_type")
        assert hasattr(p, "hihat_density")
        assert hasattr(p, "confidence")
        assert p.bar_end > p.bar_start
        assert len(p.kick) == 16 * (p.bar_end - p.bar_start)

    def test_events_have_stem_attribution(self) -> None:
        """AtomicEvent objects should have stem='drums'."""
        sr = 22050
        bpm = 120.0
        duration = 4.0
        beats, downbeats = _make_beatgrid(bpm, duration)
        total_samples = int(sr * duration)

        kick = _make_kick_impulse(sr)
        signal = _place_impulses(total_samples, kick, beats[:8], sr, amplitude=1.0)

        from scue.layer1.models import Section
        sections = [Section(label="drop", start=0.0, end=duration)]

        detector = self._get_detector()
        _, events = detector.detect(signal, sr, beats, downbeats, sections)

        for e in events:
            assert e.stem == "drums"
            assert e.source == "detector"
            assert e.bar_index is not None
            assert e.beat_position is not None
            assert 0 <= e.beat_position <= 15


# ---------------------------------------------------------------------------
# Tests: snap_to_grid utility
# ---------------------------------------------------------------------------

@needs_scipy
class TestSnapToGrid:
    """Tests for the 16th-note grid snapping utility."""

    def test_exact_grid_position(self) -> None:
        from scue.layer1.detectors.percussion_stem import _snap_to_grid

        downbeats = [0.0, 2.0, 4.0, 6.0]
        sixteenth_dur = 0.125  # 120 BPM, 16th = 125ms

        bar_idx, slot, error = _snap_to_grid(0.0, downbeats, sixteenth_dur)
        assert bar_idx == 0
        assert slot == 0
        assert error < 1.0  # < 1ms

    def test_near_grid_position(self) -> None:
        from scue.layer1.detectors.percussion_stem import _snap_to_grid

        downbeats = [0.0, 2.0, 4.0]
        sixteenth_dur = 0.125

        # 15ms late (should snap to slot 0, bar 1)
        bar_idx, slot, error = _snap_to_grid(2.015, downbeats, sixteenth_dur)
        assert bar_idx == 1
        assert slot == 0
        assert error == pytest.approx(15.0, abs=1.0)

    def test_mid_bar_position(self) -> None:
        from scue.layer1.detectors.percussion_stem import _snap_to_grid

        downbeats = [0.0, 2.0, 4.0]
        sixteenth_dur = 0.125

        # Beat 3 of bar 0 = slot 8 = 1.0s
        bar_idx, slot, error = _snap_to_grid(1.0, downbeats, sixteenth_dur)
        assert bar_idx == 0
        assert slot == 8
        assert error < 1.0

    def test_empty_downbeats(self) -> None:
        from scue.layer1.detectors.percussion_stem import _snap_to_grid

        bar_idx, slot, error = _snap_to_grid(1.0, [], 0.125)
        assert bar_idx == 0
        assert slot == 0


# ---------------------------------------------------------------------------
# Tests: Config loading
# ---------------------------------------------------------------------------

class TestStemDrumConfig:
    """Tests for stem drum detector configuration."""

    def test_default_config(self) -> None:
        from scue.layer1.detectors.percussion_stem import StemDrumConfig

        cfg = StemDrumConfig()
        assert cfg.bands["kick"] == (20, 200)
        assert cfg.bands["snare"] == (200, 5000)
        assert cfg.bands["hihat"] == (5000, 16000)
        assert cfg.sensitivity["kick"] == 1.5
        assert cfg.min_ioi_ms["hihat"] == 30
        assert cfg.max_snap_error_ms == 25.0

    def test_config_from_yaml(self) -> None:
        """Config loading from detectors.yaml should include stem_percussion."""
        from scue.layer1.detectors.percussion_stem import _load_stem_config

        cfg = _load_stem_config()
        # Should have loaded from YAML or fallen back to defaults
        assert "kick" in cfg.bands
        assert "snare" in cfg.bands
        assert "hihat" in cfg.bands
