"""Change-point detection using ruptures.

Finds structural boundaries in stacked audio features that the
ML model may have missed.
"""

import librosa
import numpy as np
import ruptures as rpt


def detect_boundaries(
    feature_matrix: np.ndarray,
    sr: int,
    hop_length: int,
    penalty: float = 5.0,
    min_section_sec: float = 4.0,
) -> list[float]:
    """Detect change points in the feature matrix.

    Args:
        feature_matrix: shape (n_frames, n_features), z-score normalized
        sr: audio sample rate
        hop_length: librosa hop length used for features
        penalty: ruptures penalty (lower = more breakpoints)
        min_section_sec: minimum section length in seconds

    Returns:
        List of boundary timestamps in seconds.
    """
    # Downsample for speed — KernelCPD is O(n^2) on full resolution
    downsample = 4
    reduced = feature_matrix[::downsample]

    # min_size in downsampled frames
    frames_per_sec = sr / hop_length
    min_size = max(2, int((min_section_sec * frames_per_sec) / downsample))

    algo = rpt.KernelCPD(kernel="rbf", min_size=min_size).fit(reduced)
    bkps = algo.predict(pen=penalty)

    # Convert frame indices back to timestamps (skip last = signal end)
    timestamps = []
    for bk in bkps[:-1]:
        frame_idx = bk * downsample
        time_sec = float(
            librosa.frames_to_time(frame_idx, sr=sr, hop_length=hop_length)
        )
        timestamps.append(time_sec)

    return timestamps
