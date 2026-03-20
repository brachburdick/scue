"""Librosa-based audio feature extraction.

Extracts spectral, rhythmic, and timbral features used by downstream
detectors (sections, flow model, snap). All features are computed at
a consistent sample rate and hop length.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Audio loading parameters
SR = 22050
HOP_LENGTH = 512
N_FFT = 2048


@dataclass
class AudioFeatures:
    """Container for all extracted audio features."""
    signal: Any              # np.ndarray — raw waveform
    sr: int = SR
    hop_length: int = HOP_LENGTH
    duration: float = 0.0

    # Per-frame features (shape: n_frames or (n_bands, n_frames))
    rms: Any = None                  # (n_frames,)
    spectral_centroid: Any = None    # (n_frames,)
    spectral_flux: Any = None        # (n_frames,) — onset strength envelope
    chroma: Any = None               # (12, n_frames)
    mfcc: Any = None                 # (13, n_frames)
    spectral_contrast: Any = None    # (7, n_frames)
    onset_strength: Any = None       # (n_frames,)
    tempogram: Any = None            # (384, n_frames)

    # M7 extended features — event detection
    spectral_flatness: Any = None    # (n_frames,) — tonality measure (0=tonal, 1=noisy)
    spectral_bandwidth: Any = None   # (n_frames,) — spectral spread in Hz
    y_harmonic: Any = None           # HPSS harmonic component (time-domain)
    y_percussive: Any = None         # HPSS percussive component (time-domain)

    # Stacked normalized feature matrix for change-point detection
    stacked_matrix: Any = None       # (n_frames, n_features)


def extract_all(audio_path: str) -> AudioFeatures:
    """Extract all audio features from an audio file.

    Args:
        audio_path: Path to the audio file.

    Returns:
        AudioFeatures with all fields populated.
    """
    import librosa

    logger.info("Loading audio: %s", audio_path)
    signal, sr = librosa.load(audio_path, sr=SR, mono=True)
    duration = librosa.get_duration(y=signal, sr=sr)
    logger.info("Loaded %.1fs of audio at %d Hz", duration, sr)

    features = AudioFeatures(signal=signal, sr=sr, duration=duration)

    # RMS energy envelope
    rms = librosa.feature.rms(y=signal, hop_length=HOP_LENGTH)[0]
    features.rms = rms

    # Spectral centroid (brightness/timbre)
    centroid = librosa.feature.spectral_centroid(
        y=signal, sr=sr, hop_length=HOP_LENGTH
    )[0]
    features.spectral_centroid = centroid

    # Onset strength envelope (spectral flux proxy)
    onset = librosa.onset.onset_strength(
        y=signal, sr=sr, hop_length=HOP_LENGTH
    )
    features.onset_strength = onset
    features.spectral_flux = onset  # alias — onset_strength IS spectral flux

    # Chroma (pitch class distribution)
    chroma = librosa.feature.chroma_cqt(
        y=signal, sr=sr, hop_length=HOP_LENGTH
    )
    features.chroma = chroma

    # MFCCs (timbral coefficients)
    mfcc = librosa.feature.mfcc(
        y=signal, sr=sr, hop_length=HOP_LENGTH, n_mfcc=13
    )
    features.mfcc = mfcc

    # Spectral contrast
    contrast = librosa.feature.spectral_contrast(
        y=signal, sr=sr, hop_length=HOP_LENGTH
    )
    features.spectral_contrast = contrast

    # Tempogram
    tempogram = librosa.feature.tempogram(
        onset_envelope=onset, sr=sr, hop_length=HOP_LENGTH
    )
    features.tempogram = tempogram

    # M7: Spectral flatness (tonality measure — low = tonal, high = noisy)
    flatness = librosa.feature.spectral_flatness(y=signal, hop_length=HOP_LENGTH)[0]
    features.spectral_flatness = flatness

    # M7: Spectral bandwidth (frequency spread)
    bandwidth = librosa.feature.spectral_bandwidth(
        y=signal, sr=sr, hop_length=HOP_LENGTH
    )[0]
    features.spectral_bandwidth = bandwidth

    # M7: HPSS — Harmonic-Percussive Source Separation
    # Most expensive new computation (~500ms for a 6-min track).
    # Run once here; all downstream detectors share the results.
    logger.info("Running HPSS separation...")
    y_harmonic, y_percussive = librosa.effects.hpss(signal)
    features.y_harmonic = y_harmonic
    features.y_percussive = y_percussive
    logger.info("HPSS complete")

    # Build stacked + normalized feature matrix for change-point detection
    features.stacked_matrix = _build_stacked_matrix(rms, centroid, onset, chroma, contrast)

    logger.info("Feature extraction complete: %d frames", len(rms))
    return features


def _build_stacked_matrix(
    rms: np.ndarray,
    centroid: np.ndarray,
    flux: np.ndarray,
    chroma: np.ndarray,
    contrast: np.ndarray,
) -> np.ndarray:
    """Stack features into a normalized matrix for change-point detection.

    Stack: RMS (1) + centroid (1) + flux (1) + chroma (12) + contrast (7) = 22 dims.
    Transpose to (n_frames, 22), then z-score normalize per column.
    """
    # Ensure all features have the same number of frames
    n_frames = min(len(rms), len(centroid), len(flux), chroma.shape[1], contrast.shape[1])

    stacked = np.vstack([
        rms[:n_frames].reshape(1, -1),
        centroid[:n_frames].reshape(1, -1),
        flux[:n_frames].reshape(1, -1),
        chroma[:, :n_frames],
        contrast[:, :n_frames],
    ]).T  # (n_frames, 22)

    # Z-score normalize per column
    mean = stacked.mean(axis=0, keepdims=True)
    std = stacked.std(axis=0, keepdims=True)
    std[std == 0] = 1.0  # avoid division by zero
    normalized = (stacked - mean) / std

    return normalized


def get_section_features(
    features: AudioFeatures,
    start_time: float,
    end_time: float,
) -> dict[str, float]:
    """Compute aggregate features for a time range within the track.

    Args:
        features: Full track AudioFeatures.
        start_time: Section start in seconds.
        end_time: Section end in seconds.

    Returns:
        Dict of aggregate statistics for the section.
    """
    import librosa

    start_frame = librosa.time_to_frames(start_time, sr=features.sr, hop_length=features.hop_length)
    end_frame = librosa.time_to_frames(end_time, sr=features.sr, hop_length=features.hop_length)

    # Clamp to valid range
    start_frame = max(0, start_frame)
    end_frame = min(len(features.rms), end_frame)

    if end_frame <= start_frame:
        return {
            "rms_mean": 0.0, "rms_max": 0.0, "rms_slope": 0.0,
            "centroid_mean": 0.0, "centroid_slope": 0.0,
            "flux_mean": 0.0, "onset_density": 0.0,
        }

    rms_slice = features.rms[start_frame:end_frame]
    centroid_slice = features.spectral_centroid[start_frame:end_frame]
    flux_slice = features.spectral_flux[start_frame:end_frame]

    n = len(rms_slice)
    x = np.arange(n, dtype=np.float64)

    def _slope(y: np.ndarray) -> float:
        if len(y) < 2:
            return 0.0
        # Simple linear regression slope
        x_mean = x[:len(y)].mean()
        y_mean = y.mean()
        denom = ((x[:len(y)] - x_mean) ** 2).sum()
        if denom == 0:
            return 0.0
        return float(((x[:len(y)] - x_mean) * (y - y_mean)).sum() / denom)

    # Onset density: count of significant onsets per second
    onset_threshold = features.onset_strength.mean() + features.onset_strength.std()
    onset_count = int((flux_slice > onset_threshold).sum())
    section_duration = end_time - start_time
    onset_density = onset_count / max(section_duration, 0.01)

    return {
        "rms_mean": float(rms_slice.mean()),
        "rms_max": float(rms_slice.max()),
        "rms_slope": _slope(rms_slice),
        "centroid_mean": float(centroid_slice.mean()),
        "centroid_slope": _slope(centroid_slice),
        "flux_mean": float(flux_slice.mean()),
        "onset_density": onset_density,
    }


def get_track_stats(features: AudioFeatures) -> dict[str, float]:
    """Compute track-level aggregate statistics.

    Used for normalizing per-section features (e.g., RMS ratio = section / track).
    """
    rms = features.rms
    centroid = features.spectral_centroid

    return {
        "rms_mean": float(rms.mean()),
        "rms_std": float(rms.std()),
        "rms_p75": float(np.percentile(rms, 75)),
        "centroid_mean": float(centroid.mean()),
        "centroid_median": float(np.median(centroid)),
        "centroid_std": float(centroid.std()),
        "flux_mean": float(features.spectral_flux.mean()),
    }
