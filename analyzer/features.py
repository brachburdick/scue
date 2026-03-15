"""Audio feature extraction using librosa.

Extracts spectral, energy, and rhythmic features for use by
the change-point detector and EDM section classifier.
"""

import librosa
import numpy as np

SR = 22050
HOP_LENGTH = 512
N_FFT = 2048


def extract_all(audio_path: str, sr: int = SR, hop_length: int = HOP_LENGTH) -> dict:
    """Extract all audio features from a file.

    Returns a dict with the raw signal, sample rate, hop_length,
    individual feature arrays, and a stacked/normalized matrix for ruptures.
    """
    signal, sr = librosa.load(audio_path, sr=sr)

    rms = librosa.feature.rms(y=signal, hop_length=hop_length)[0]
    centroid = librosa.feature.spectral_centroid(
        y=signal, sr=sr, hop_length=hop_length
    )[0]
    flux = librosa.onset.onset_strength(y=signal, sr=sr, hop_length=hop_length)
    chroma = librosa.feature.chroma_stft(
        y=signal, sr=sr, hop_length=hop_length, n_fft=N_FFT
    )
    mfcc = librosa.feature.mfcc(y=signal, sr=sr, hop_length=hop_length, n_mfcc=13)
    contrast = librosa.feature.spectral_contrast(
        y=signal, sr=sr, hop_length=hop_length, n_fft=N_FFT
    )
    oenv = librosa.onset.onset_strength(y=signal, sr=sr, hop_length=hop_length)
    tempogram = librosa.feature.tempogram(
        onset_envelope=oenv, sr=sr, hop_length=hop_length
    )

    n_frames = rms.shape[0]

    features = {
        "signal": signal,
        "sr": sr,
        "hop_length": hop_length,
        "n_frames": n_frames,
        "rms": rms,
        "spectral_centroid": centroid,
        "spectral_flux": flux[:n_frames],
        "chroma": chroma[:, :n_frames],
        "mfcc": mfcc[:, :n_frames],
        "spectral_contrast": contrast[:, :n_frames],
        "onset_strength": oenv[:n_frames],
        "tempogram": tempogram[:, :n_frames],
    }

    features["stacked_matrix"] = _build_stacked_matrix(features)
    return features


def _build_stacked_matrix(features: dict) -> np.ndarray:
    """Stack and z-score normalize features into (n_frames, n_dims) matrix."""
    n = features["n_frames"]

    components = [
        features["rms"].reshape(1, n),
        features["spectral_centroid"].reshape(1, n),
        features["spectral_flux"].reshape(1, n),
        features["chroma"][:, :n],
        features["spectral_contrast"][:, :n],
    ]
    # shape: (n_dims, n_frames)
    stacked = np.vstack(components)
    # transpose to (n_frames, n_dims)
    matrix = stacked.T

    # z-score normalize each dimension
    mean = matrix.mean(axis=0, keepdims=True)
    std = matrix.std(axis=0, keepdims=True)
    std[std == 0] = 1.0
    matrix = (matrix - mean) / std

    return matrix


def get_section_features(
    features: dict, start_time: float, end_time: float
) -> dict:
    """Compute aggregate features for a time range (used by EDM classifier)."""
    sr = features["sr"]
    hop = features["hop_length"]

    start_frame = librosa.time_to_frames(start_time, sr=sr, hop_length=hop)
    end_frame = librosa.time_to_frames(end_time, sr=sr, hop_length=hop)
    end_frame = min(end_frame, features["n_frames"])

    if end_frame <= start_frame:
        start_frame = max(0, end_frame - 1)

    rms_slice = features["rms"][start_frame:end_frame]
    centroid_slice = features["spectral_centroid"][start_frame:end_frame]
    flux_slice = features["spectral_flux"][start_frame:end_frame]
    onset_slice = features["onset_strength"][start_frame:end_frame]

    duration = end_time - start_time

    def safe_slope(arr):
        if len(arr) < 2:
            return 0.0
        x = np.arange(len(arr))
        return float(np.polyfit(x, arr, 1)[0])

    return {
        "rms_mean": float(np.mean(rms_slice)) if len(rms_slice) > 0 else 0.0,
        "rms_max": float(np.max(rms_slice)) if len(rms_slice) > 0 else 0.0,
        "rms_slope": safe_slope(rms_slice),
        "rms_values": rms_slice,
        "centroid_mean": float(np.mean(centroid_slice)) if len(centroid_slice) > 0 else 0.0,
        "centroid_slope": safe_slope(centroid_slice),
        "flux_mean": float(np.mean(flux_slice)) if len(flux_slice) > 0 else 0.0,
        "onset_density": float(np.sum(onset_slice > np.mean(onset_slice))) / max(duration, 0.1),
        "duration": duration,
    }


def get_track_stats(features: dict) -> dict:
    """Compute track-level statistics for relative comparisons."""
    rms = features["rms"]
    centroid = features["spectral_centroid"]
    flux = features["spectral_flux"]

    return {
        "rms_mean": float(np.mean(rms)),
        "rms_std": float(np.std(rms)),
        "rms_p75": float(np.percentile(rms, 75)),
        "centroid_mean": float(np.mean(centroid)),
        "centroid_median": float(np.median(centroid)),
        "centroid_std": float(np.std(centroid)),
        "flux_mean": float(np.mean(flux)),
    }
