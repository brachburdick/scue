"""Section boundary detection — Tier 1, Stage 1 of the analysis pipeline.

Combines two boundary sources:
  1. ML-based structure analysis via allin1-mlx (Apple Silicon)
  2. Ruptures KernelCPD change-point detection on stacked audio features

The two sets of boundaries are then merged. The result feeds into the
8-bar snapping pass (TODO: Milestone 1) and the EDM flow model labeler.
"""

import librosa
import numpy as np
import ruptures as rpt
import allin1_mlx


def analyze_structure(audio_path: str) -> dict:
    """Run allin1_mlx (Apple Silicon) structure analysis and return normalized result dict.

    Returns:
        { bpm, beats, downbeats, segments: [{ label, start, end }] }
    """
    result = allin1_mlx.analyze(audio_path)

    return {
        "bpm": float(result.bpm),
        "beats": [float(b) for b in result.beats],
        "downbeats": [float(d) for d in result.downbeats],
        "segments": [
            {
                "label": seg.label,
                "start": float(seg.start),
                "end": float(seg.end),
            }
            for seg in result.segments
        ],
    }


def detect_boundaries(
    feature_matrix: np.ndarray,
    sr: int,
    hop_length: int,
    penalty: float = 5.0,
    min_section_sec: float = 4.0,
) -> list[float]:
    """Detect change points in the feature matrix using ruptures KernelCPD.

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


# TODO(milestone-1): implement 8-bar snapping pass here
# After detect_boundaries() returns raw timestamps, snap each boundary to the
# nearest 8-bar grid line derived from the downbeat list.
# If a boundary is within ~1 bar of an 8-bar grid line, snap it.
# If it's far from any grid line, keep it but set irregular_phrase=True.
# See docs/ARCHITECTURE.md → Sub-layer 1A → "The 8-bar structural prior"
def snap_to_8bar_grid(
    boundaries: list[float],
    downbeats: list[float],
    snap_tolerance_bars: float = 1.0,
) -> list[dict]:
    """Snap boundaries to the nearest 8-bar grid line.

    Args:
        boundaries: raw boundary timestamps in seconds
        downbeats: downbeat timestamps in seconds
        snap_tolerance_bars: how close (in bars) a boundary must be to snap

    Returns:
        List of { time, irregular_phrase, bar_count, expected_bar_count }
    """
    # TODO: implement
    # Placeholder: return boundaries unchanged with no metadata
    return [{"time": t, "irregular_phrase": False, "bar_count": 0, "expected_bar_count": 0}
            for t in boundaries]
