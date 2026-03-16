"""8-bar snapping pass for section boundaries.

EDM tracks overwhelmingly follow 8-bar (or multiple-of-8) phrase structure.
This module snaps section boundaries to the nearest downbeat grid line that
produces an 8-bar-aligned section, and flags sections that don't conform.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from ..models import Section

logger = logging.getLogger(__name__)

# Maximum distance (in bars) a boundary can be snapped
MAX_SNAP_BARS = 1.0

# Standard phrase lengths in bars (multiples of 8)
STANDARD_PHRASE_LENGTHS = [4, 8, 16, 32, 64]


@dataclass
class SnapResult:
    """Result of the 8-bar snapping pass."""
    sections: list[Section]
    snap_report: list[str]  # human-readable log of snap decisions


def snap_to_8bar_grid(
    raw_sections: list[dict],
    downbeats: list[float],
    bpm: float,
) -> SnapResult:
    """Snap section boundaries to the nearest 8-bar grid lines.

    Args:
        raw_sections: List of dicts with 'label', 'start', 'end', 'original_label',
                      'confidence' from the merged boundary detection.
        downbeats: Downbeat timestamps in seconds (every bar).
        bpm: Track BPM for bar duration calculation.

    Returns:
        SnapResult with snapped Section objects and a report.
    """
    if not downbeats or not raw_sections or bpm <= 0:
        return SnapResult(
            sections=[
                Section(
                    label=s["label"],
                    start=s["start"],
                    end=s["end"],
                    original_label=s.get("original_label", s["label"]),
                    confidence=s.get("confidence", 0.5),
                )
                for s in raw_sections
            ],
            snap_report=["No downbeats or BPM available — skipping snap"],
        )

    downbeat_arr = np.array(downbeats)
    bar_duration = 60.0 / bpm * 4  # 4 beats per bar
    max_snap_sec = MAX_SNAP_BARS * bar_duration

    report: list[str] = []

    # Step 1: Snap each boundary to the nearest downbeat
    snapped_boundaries: list[float] = []
    for section in raw_sections:
        for boundary in [section["start"], section["end"]]:
            if boundary not in [b for b in snapped_boundaries]:
                snapped = _snap_to_nearest_downbeat(boundary, downbeat_arr, max_snap_sec)
                snapped_boundaries.append(snapped)

    # Deduplicate and sort
    snapped_boundaries = sorted(set(snapped_boundaries))

    # Step 2: Rebuild sections from snapped boundaries, matching labels
    sections: list[Section] = []
    for i in range(len(snapped_boundaries) - 1):
        start = snapped_boundaries[i]
        end = snapped_boundaries[i + 1]

        # Find the original section that best overlaps this snapped range
        midpoint = (start + end) / 2
        best_match = _find_matching_section(midpoint, raw_sections)

        # Count bars
        bars_in_section = _count_bars(start, end, downbeat_arr)
        expected = _nearest_standard_length(bars_in_section)
        irregular = bars_in_section != expected

        label = best_match["label"]
        original_label = best_match.get("original_label", label)

        section = Section(
            label=label,
            start=round(start, 4),
            end=round(end, 4),
            confidence=best_match.get("confidence", 0.5),
            bar_count=bars_in_section,
            expected_bar_count=expected,
            irregular_phrase=irregular,
            original_label=original_label,
        )
        sections.append(section)

        if irregular:
            report.append(
                f"  [{label}] {start:.1f}s–{end:.1f}s: {bars_in_section} bars "
                f"(expected {expected}) — IRREGULAR"
            )
        else:
            report.append(
                f"  [{label}] {start:.1f}s–{end:.1f}s: {bars_in_section} bars — OK"
            )

    logger.info("8-bar snap complete: %d sections, %d irregular",
                len(sections), sum(1 for s in sections if s.irregular_phrase))

    return SnapResult(sections=sections, snap_report=report)


def _snap_to_nearest_downbeat(
    time_sec: float,
    downbeats: np.ndarray,
    max_snap_sec: float,
) -> float:
    """Snap a timestamp to the nearest downbeat within the snap window.

    If no downbeat is within max_snap_sec, return the original time.
    """
    if len(downbeats) == 0:
        return time_sec

    distances = np.abs(downbeats - time_sec)
    nearest_idx = int(np.argmin(distances))
    nearest_distance = distances[nearest_idx]

    if nearest_distance <= max_snap_sec:
        return float(downbeats[nearest_idx])
    return time_sec


def _count_bars(start: float, end: float, downbeats: np.ndarray) -> int:
    """Count the number of bars (downbeats) within a time range."""
    mask = (downbeats >= start - 0.01) & (downbeats < end - 0.01)
    return max(1, int(mask.sum()))


def _nearest_standard_length(bar_count: int) -> int:
    """Find the nearest standard phrase length (multiple of 8, or 4)."""
    if bar_count <= 0:
        return 4

    best = STANDARD_PHRASE_LENGTHS[0]
    best_dist = abs(bar_count - best)

    for length in STANDARD_PHRASE_LENGTHS:
        dist = abs(bar_count - length)
        if dist < best_dist:
            best = length
            best_dist = dist

    return best


def _find_matching_section(midpoint: float, raw_sections: list[dict]) -> dict:
    """Find the raw section whose range contains the given midpoint."""
    for section in raw_sections:
        if section["start"] <= midpoint <= section["end"]:
            return section
    # Fallback: return the closest section
    return min(raw_sections, key=lambda s: abs((s["start"] + s["end"]) / 2 - midpoint))
