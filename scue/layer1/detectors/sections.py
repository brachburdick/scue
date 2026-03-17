"""Section boundary detection via allin1-mlx and ruptures.

Two-stage boundary detection:
1. allin1-mlx: ML-based structure analysis (BPM, beats, downbeats, labeled sections)
2. ruptures KernelCPD: spectral change-point detection for splitting long sections

The results are merged with a tolerance window to avoid duplicate boundaries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# Boundary merge tolerance: boundaries within this many seconds are considered duplicates
BOUNDARY_TOLERANCE_SEC = 2.0

# Minimum section duration for ruptures to consider splitting
MIN_SECTION_SEC = 6.0


@dataclass
class RawSection:
    """A section from allin1-mlx before EDM relabeling."""
    label: str
    start: float
    end: float


@dataclass
class StructureResult:
    """Combined result from ML structure analysis."""
    bpm: float
    beats: list[float]
    downbeats: list[float]
    sections: list[RawSection]
    source: str = "allin1"  # "allin1" or "fallback"


def analyze_structure(audio_path: str) -> StructureResult:
    """Run allin1-mlx structure analysis on an audio file.

    Falls back to librosa-only analysis if allin1-mlx is not available.

    Args:
        audio_path: Path to the audio file.

    Returns:
        StructureResult with BPM, beats, downbeats, and raw sections.
    """
    try:
        return _analyze_with_allin1(audio_path)
    except ImportError:
        logger.warning("allin1-mlx not available, falling back to librosa-only analysis")
        return _analyze_fallback(audio_path)


def _find_weights_dir() -> str | None:
    """Locate the mlx-weights directory relative to the project root.

    Searches upward from this file's directory for mlx-weights/.
    """
    from pathlib import Path

    current = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = current / "mlx-weights"
        if candidate.is_dir():
            return str(candidate)
        current = current.parent
    return None


def _analyze_with_allin1(audio_path: str) -> StructureResult:
    """Analyze structure using allin1-mlx (Apple Silicon ML model).

    Raises ImportError if allin1-mlx is not installed.
    """
    import allin1_mlx  # noqa: F811 — will raise ImportError if missing

    weights_dir = _find_weights_dir()
    logger.info("Running allin1-mlx analysis on: %s (weights: %s)", audio_path, weights_dir)

    kwargs: dict = {}
    if weights_dir:
        kwargs["mlx_weights_dir"] = weights_dir

    result = allin1_mlx.analyze(audio_path, **kwargs)

    sections = [
        RawSection(
            label=seg.label,
            start=seg.start,
            end=seg.end,
        )
        for seg in result.segments
    ]

    return StructureResult(
        bpm=result.bpm,
        beats=list(result.beats),
        downbeats=list(result.downbeats),
        sections=sections,
        source="allin1",
    )


def _analyze_fallback(audio_path: str) -> StructureResult:
    """Fallback analysis using only librosa (no ML model).

    Provides BPM and beat tracking but no section labels. Sections
    will be derived entirely from ruptures change-point detection.
    """
    import librosa

    from .features import HOP_LENGTH, SR

    logger.info("Running librosa-only fallback analysis on: %s", audio_path)
    y, sr = librosa.load(audio_path, sr=SR, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    # Beat tracking
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=HOP_LENGTH)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=HOP_LENGTH).tolist()

    # Extract scalar BPM from tempo
    bpm = float(np.atleast_1d(tempo)[0])

    # Downbeats: every 4th beat (approximate without ML)
    downbeats = beat_times[::4] if beat_times else []

    # No sections from fallback — the pipeline will create one big section
    # that ruptures can split
    sections = [RawSection(label="unknown", start=0.0, end=duration)]

    return StructureResult(
        bpm=bpm,
        beats=beat_times,
        downbeats=downbeats,
        sections=sections,
        source="fallback",
    )


def detect_boundaries(
    feature_matrix: np.ndarray,
    sr: int,
    hop_length: int,
    penalty: float = 5.0,
    min_section_sec: float = MIN_SECTION_SEC,
) -> list[float]:
    """Detect change-point boundaries using ruptures KernelCPD.

    Args:
        feature_matrix: Stacked feature matrix (n_frames, n_features).
        sr: Audio sample rate.
        hop_length: Hop length used for feature extraction.
        penalty: Ruptures penalty parameter. Lower = more breakpoints.
        min_section_sec: Minimum section length in seconds.

    Returns:
        List of boundary timestamps in seconds (excluding track end).
    """
    import librosa
    import ruptures

    n_frames = feature_matrix.shape[0]

    # Downsample by 4x for performance (ruptures is O(n²))
    downsample_factor = 4
    downsampled = feature_matrix[::downsample_factor]

    min_size = max(2, int(min_section_sec * sr / (hop_length * downsample_factor)))

    logger.info(
        "Running ruptures KernelCPD: %d frames (downsampled from %d), penalty=%.1f",
        len(downsampled), n_frames, penalty,
    )

    algo = ruptures.KernelCPD(kernel="rbf", min_size=min_size).fit(downsampled)
    try:
        breakpoints = algo.predict(pen=penalty)
    except ruptures.exceptions.BadSegmentationParameters:
        logger.warning(
            "Audio too short for change-point detection (%d frames) — returning no boundaries",
            len(downsampled),
        )
        return []

    # Convert frame indices back to time
    # breakpoints from ruptures are 1-indexed and include the final sample
    times = []
    for bp in breakpoints[:-1]:  # exclude final (track end)
        frame_idx = bp * downsample_factor
        time_sec = librosa.frames_to_time(frame_idx, sr=sr, hop_length=hop_length)
        times.append(float(time_sec))

    logger.info("Ruptures detected %d boundaries: %s", len(times),
                [f"{t:.1f}s" for t in times])
    return times


def merge_boundaries(
    allin1_sections: list[RawSection],
    ruptures_boundaries: list[float],
    tolerance: float = BOUNDARY_TOLERANCE_SEC,
) -> list[RawSection]:
    """Merge allin1 sections with ruptures boundaries.

    Ruptures boundaries only add NEW splits within existing sections that
    are longer than MIN_SECTION_SEC. They do not override allin1 boundaries.

    If a ruptures boundary falls within `tolerance` seconds of an existing
    allin1 boundary, it is discarded as a duplicate.

    Args:
        allin1_sections: Sections from allin1-mlx (or fallback).
        ruptures_boundaries: Boundary timestamps from ruptures.
        tolerance: Merge tolerance in seconds.

    Returns:
        Updated list of RawSections, potentially with long sections split.
    """
    if not ruptures_boundaries:
        return allin1_sections

    # Collect existing boundaries from allin1
    existing_boundaries = set()
    for section in allin1_sections:
        existing_boundaries.add(section.start)
        existing_boundaries.add(section.end)

    # Filter ruptures boundaries: only keep those far enough from existing ones
    novel_boundaries: list[float] = []
    for rb in ruptures_boundaries:
        is_duplicate = any(
            abs(rb - eb) < tolerance for eb in existing_boundaries
        )
        if not is_duplicate:
            novel_boundaries.append(rb)

    if not novel_boundaries:
        return allin1_sections

    logger.info("Merging %d novel ruptures boundaries into sections", len(novel_boundaries))

    # Split sections at novel boundaries
    result: list[RawSection] = []
    for section in allin1_sections:
        # Find novel boundaries that fall within this section
        splits = sorted([
            b for b in novel_boundaries
            if section.start + tolerance < b < section.end - tolerance
        ])

        if not splits or section.end - section.start < MIN_SECTION_SEC:
            result.append(section)
            continue

        # Split this section
        boundaries = [section.start] + splits + [section.end]
        for i in range(len(boundaries) - 1):
            result.append(RawSection(
                label=section.label,
                start=boundaries[i],
                end=boundaries[i + 1],
            ))

    return result
