"""Edge case tests for the analysis pipeline.

Uses programmatically generated audio (numpy + soundfile) to test
boundary conditions: very short tracks, silence, no detectable beats,
corrupted files.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from scue.layer1.analysis import run_analysis
from scue.layer1.fingerprint import compute_fingerprint


def _write_wav(path: Path, signal: np.ndarray, sr: int = 22050) -> None:
    """Write a mono float32 WAV file."""
    sf.write(str(path), signal.astype(np.float32), sr)


def _sine_wave(duration_s: float, freq: float = 440.0, sr: int = 22050) -> np.ndarray:
    """Generate a sine wave."""
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    return 0.5 * np.sin(2 * np.pi * freq * t)


def _silence(duration_s: float, sr: int = 22050) -> np.ndarray:
    """Generate silence."""
    return np.zeros(int(sr * duration_s), dtype=np.float32)


def _noise(duration_s: float, sr: int = 22050) -> np.ndarray:
    """Generate white noise."""
    rng = np.random.default_rng(42)
    return (rng.random(int(sr * duration_s)) * 2 - 1).astype(np.float32) * 0.3


class TestVeryShortTrack:
    """Tracks under 5 seconds — should produce a valid analysis, not crash."""

    def test_2_second_sine(self, tmp_path: Path) -> None:
        audio_path = tmp_path / "short.wav"
        _write_wav(audio_path, _sine_wave(2.0))

        result = run_analysis(audio_path, skip_waveform=True)

        assert result.fingerprint == compute_fingerprint(audio_path)
        assert result.duration > 0
        assert len(result.sections) >= 1
        # BPM may be None or 0.0 for very short tracks where librosa can't detect beats
        assert result.bpm is None or result.bpm >= 0

    def test_1_second_sine(self, tmp_path: Path) -> None:
        audio_path = tmp_path / "very_short.wav"
        _write_wav(audio_path, _sine_wave(1.0))

        result = run_analysis(audio_path, skip_waveform=True)

        assert result.fingerprint
        assert result.duration > 0
        # With only 1 second, we should still get at least one section
        assert len(result.sections) >= 1


class TestSilenceTrack:
    """Pure silence — analysis should complete with low-energy results."""

    def test_silence_5_seconds(self, tmp_path: Path) -> None:
        audio_path = tmp_path / "silence.wav"
        _write_wav(audio_path, _silence(5.0))

        result = run_analysis(audio_path, skip_waveform=True)

        assert result.fingerprint
        assert result.duration > 0
        assert len(result.sections) >= 1
        # Energy curve should be near-zero
        if result.features.energy_curve:
            max_energy = max(result.features.energy_curve)
            assert max_energy < 0.01, f"Silence energy too high: {max_energy}"


class TestNoBeatTrack:
    """White noise with no rhythmic content — beat detection may return empty."""

    def test_noise_no_beats(self, tmp_path: Path) -> None:
        audio_path = tmp_path / "noise.wav"
        _write_wav(audio_path, _noise(5.0))

        result = run_analysis(audio_path, skip_waveform=True)

        assert result.fingerprint
        assert result.duration > 0
        assert len(result.sections) >= 1
        # BPM may be None or float for noise — either way, no crash
        assert result.bpm is None or isinstance(result.bpm, (int, float))


class TestCorruptedFile:
    """Non-audio file or truncated file — should raise a clear error."""

    def test_non_audio_file_raises(self, tmp_path: Path) -> None:
        bad_path = tmp_path / "not_audio.wav"
        bad_path.write_text("this is not audio data")

        # soundfile/librosa should raise, and it should propagate
        with pytest.raises(Exception):
            run_analysis(bad_path, skip_waveform=True)

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.wav"

        with pytest.raises(FileNotFoundError):
            run_analysis(missing, skip_waveform=True)


class TestPersistence:
    """Analysis results can be stored and retrieved."""

    def test_store_and_skip_reanalysis(self, tmp_path: Path) -> None:
        audio_path = tmp_path / "track.wav"
        _write_wav(audio_path, _sine_wave(3.0))
        tracks_dir = tmp_path / "tracks"
        tracks_dir.mkdir()

        # First run
        result1 = run_analysis(audio_path, tracks_dir=str(tracks_dir), skip_waveform=True)
        assert result1.version == 1

        # Second run — should reuse existing
        result2 = run_analysis(audio_path, tracks_dir=str(tracks_dir), skip_waveform=True)
        assert result2.fingerprint == result1.fingerprint

    def test_force_reanalysis(self, tmp_path: Path) -> None:
        audio_path = tmp_path / "track.wav"
        _write_wav(audio_path, _sine_wave(3.0))
        tracks_dir = tmp_path / "tracks"
        tracks_dir.mkdir()

        result1 = run_analysis(audio_path, tracks_dir=str(tracks_dir), skip_waveform=True)
        result2 = run_analysis(audio_path, tracks_dir=str(tracks_dir), skip_waveform=True, force=True)

        # Both should have the same fingerprint
        assert result2.fingerprint == result1.fingerprint
