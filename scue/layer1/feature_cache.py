"""Librosa feature cache — save/load frame-level arrays to disk.

Extracts librosa features once, reuses across base analysis and tier pipelines.
Features are stored as .npz files in the track's directory.

NOT cached: signal, y_harmonic, y_percussive (large time-domain arrays, cheap to reload).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .detectors.features import AudioFeatures

logger = logging.getLogger(__name__)

# Feature arrays to persist in the .npz cache
_CACHED_ARRAYS = (
    "rms",
    "spectral_centroid",
    "onset_strength",
    "chroma",
    "mfcc",
    "spectral_contrast",
    "tempogram",
    "spectral_flatness",
    "spectral_bandwidth",
    "stacked_matrix",
)


def save_features(fingerprint: str, features: AudioFeatures, tracks_dir: Path) -> Path:
    """Save frame-level feature arrays to tracks/{fp}/features.npz.

    Args:
        fingerprint: Track fingerprint (used as directory name).
        features: Extracted AudioFeatures object.
        tracks_dir: Base tracks directory.

    Returns:
        Path to the saved .npz file.
    """
    feat_dir = tracks_dir / fingerprint
    feat_dir.mkdir(parents=True, exist_ok=True)
    npz_path = feat_dir / "features.npz"

    arrays: dict[str, np.ndarray] = {
        "sr": np.array([features.sr]),
        "duration": np.array([features.duration]),
        "hop_length": np.array([features.hop_length]),
    }

    for name in _CACHED_ARRAYS:
        arr = getattr(features, name, None)
        if arr is not None:
            arrays[name] = np.asarray(arr)

    np.savez_compressed(npz_path, **arrays)
    logger.info("Feature cache saved: %s (%d arrays)", npz_path, len(arrays))
    return npz_path


def load_features(fingerprint: str, tracks_dir: Path) -> AudioFeatures | None:
    """Load cached features from tracks/{fp}/features.npz.

    Returns AudioFeatures with signal=None (time-domain arrays not cached).
    Returns None on cache miss.
    """
    npz_path = tracks_dir / fingerprint / "features.npz"
    if not npz_path.exists():
        return None

    try:
        data = np.load(npz_path, allow_pickle=False)
    except Exception:
        logger.warning("Failed to load feature cache: %s", npz_path, exc_info=True)
        return None

    sr = int(data["sr"][0]) if "sr" in data else 22050
    duration = float(data["duration"][0]) if "duration" in data else 0.0
    hop_length = int(data["hop_length"][0]) if "hop_length" in data else 512

    features = AudioFeatures(signal=None, sr=sr, duration=duration, hop_length=hop_length)

    for name in _CACHED_ARRAYS:
        if name in data:
            setattr(features, name, data[name])

    # Alias: spectral_flux = onset_strength
    if features.onset_strength is not None:
        features.spectral_flux = features.onset_strength

    logger.info("Feature cache loaded: %s", npz_path)
    return features
