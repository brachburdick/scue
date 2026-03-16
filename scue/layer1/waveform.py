"""RGB waveform computation for track visualization.

Produces a 3-band waveform (R=bass, G=mids, B=highs) at 60 FPS for
the frontend track detail view. Each band is the RMS energy of a
frequency sub-band, normalized to 0.0–1.0.
"""

from __future__ import annotations

import logging

import numpy as np

from .models import RGBWaveform

logger = logging.getLogger(__name__)

# Frequency band boundaries (Hz)
LOW_BAND = (0, 250)
MID_BAND = (250, 4000)
HIGH_BAND = (4000, 11025)  # up to Nyquist at 22050 Hz

# Output sample rate (frames per second)
WAVEFORM_FPS = 60


def compute_rgb_waveform(
    signal: np.ndarray,
    sr: int = 22050,
    fps: int = WAVEFORM_FPS,
) -> RGBWaveform:
    """Compute 3-band RGB waveform from audio signal.

    Args:
        signal: Mono audio signal.
        sr: Sample rate.
        fps: Output frames per second.

    Returns:
        RGBWaveform with low/mid/high bands at the given fps.
    """
    import librosa

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

    low = _band_rms(*LOW_BAND)
    mid = _band_rms(*MID_BAND)
    high = _band_rms(*HIGH_BAND)

    # Normalize each band to 0.0–1.0
    def _normalize(arr: np.ndarray) -> list[float]:
        max_val = arr.max()
        if max_val == 0:
            return [0.0] * len(arr)
        normalized = arr / max_val
        return normalized.tolist()

    # Resample to exact output frame count
    def _resample(arr: np.ndarray, target_len: int) -> np.ndarray:
        if len(arr) == target_len:
            return arr
        indices = np.linspace(0, len(arr) - 1, target_len)
        return np.interp(indices, np.arange(len(arr)), arr)

    low_resampled = _resample(low, n_output_frames)
    mid_resampled = _resample(mid, n_output_frames)
    high_resampled = _resample(high, n_output_frames)

    return RGBWaveform(
        sample_rate=fps,
        duration=duration,
        low=_normalize(low_resampled),
        mid=_normalize(mid_resampled),
        high=_normalize(high_resampled),
    )
