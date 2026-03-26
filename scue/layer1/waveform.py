"""RGB waveform computation for track visualization.

Produces a 3-band waveform (low/mid/high) at 150 FPS for the frontend
track detail view. Each band is the RMS energy of a frequency sub-band,
normalized globally (all bands share the same max) to preserve the
actual frequency balance of the music.

Frequency crossovers match Pioneer mixer EQ points:
  LOW:  20–200 Hz
  MID:  200–2500 Hz
  HIGH: 2500 Hz–Nyquist
"""

from __future__ import annotations

import logging

import numpy as np

from .models import RGBWaveform

logger = logging.getLogger(__name__)

# Frequency band boundaries (Hz) — aligned with Pioneer mixer EQ crossovers
LOW_BAND = (20, 200)
MID_BAND = (200, 2500)
HIGH_BAND = (2500, 22050)

# Output sample rate — matches Pioneer detail waveform resolution (150 entries/sec)
WAVEFORM_FPS = 150


def compute_rgb_waveform(
    signal: np.ndarray,
    sr: int = 22050,
    fps: int = WAVEFORM_FPS,
    low_band: tuple[int, int] | None = None,
    mid_band: tuple[int, int] | None = None,
    high_band: tuple[int, int] | None = None,
) -> RGBWaveform:
    """Compute 3-band RGB waveform from audio signal.

    Args:
        signal: Mono audio signal.
        sr: Sample rate.
        fps: Output frames per second.
        low_band: Optional custom low frequency range (Hz). Defaults to LOW_BAND.
        mid_band: Optional custom mid frequency range (Hz). Defaults to MID_BAND.
        high_band: Optional custom high frequency range (Hz). Defaults to HIGH_BAND.

    Returns:
        RGBWaveform with low/mid/high bands at the given fps.
    """
    import librosa

    lb = low_band or LOW_BAND
    mb = mid_band or MID_BAND
    hb = high_band or HIGH_BAND

    duration = len(signal) / sr
    n_output_frames = int(duration * fps)

    if n_output_frames == 0:
        return RGBWaveform(sample_rate=fps, duration=duration)

    # Compute STFT
    n_fft = 2048
    hop_length = max(1, len(signal) // n_output_frames)
    stft = np.abs(librosa.stft(signal, n_fft=n_fft, hop_length=hop_length))

    # Frequency bins
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    def _band_rms(low_hz: float, high_hz: float) -> np.ndarray:
        mask = (freqs >= low_hz) & (freqs < high_hz)
        if not mask.any():
            return np.zeros(stft.shape[1])
        return np.sqrt(np.mean(stft[mask] ** 2, axis=0))

    low = _band_rms(*lb)
    mid = _band_rms(*mb)
    high = _band_rms(*hb)

    # Resample to exact output frame count
    def _resample(arr: np.ndarray, target_len: int) -> np.ndarray:
        if len(arr) == target_len:
            return arr
        indices = np.linspace(0, len(arr) - 1, target_len)
        return np.interp(indices, np.arange(len(arr)), arr)

    low_resampled = _resample(low, n_output_frames)
    mid_resampled = _resample(mid, n_output_frames)
    high_resampled = _resample(high, n_output_frames)

    # Global normalization — all bands share the same max so relative
    # frequency balance is preserved (a bass-heavy track stays bass-heavy)
    global_max = max(low_resampled.max(), mid_resampled.max(), high_resampled.max())

    def _normalize(arr: np.ndarray) -> list[float]:
        if global_max == 0:
            return [0.0] * len(arr)
        return (arr / global_max).tolist()

    return RGBWaveform(
        sample_rate=fps,
        duration=duration,
        low=_normalize(low_resampled),
        mid=_normalize(mid_resampled),
        high=_normalize(high_resampled),
    )
