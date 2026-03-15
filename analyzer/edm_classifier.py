"""EDM-specific section classification heuristics.

Maps generic music structure labels (verse, chorus, break, etc.)
to EDM vocabulary (drop, build, fakeout, breakdown) using energy
profiles, spectral characteristics, and section ordering.
"""

import numpy as np
from .features import get_section_features, get_track_stats


# --- Label mapping from allin1 generic labels to EDM candidates ---

DIRECT_MAP = {
    "intro": "intro",
    "outro": "outro",
}

# Labels that need context-dependent classification
CONTEXT_LABELS = {"chorus", "verse", "break", "bridge", "inst", "solo", "start", "end"}


def classify_sections(segments: list[dict], features: dict) -> list[dict]:
    """Classify segments with EDM-specific labels.

    Args:
        segments: list of {"label", "start", "end"} dicts (from merged boundaries)
        features: full feature dict from features.extract_all()

    Returns:
        Same segments with "label" updated to EDM vocabulary and
        "original_label" preserving the allin1 label.
    """
    track_stats = get_track_stats(features)

    # Step 1: Compute per-section features
    for seg in segments:
        seg["original_label"] = seg["label"]
        seg["features"] = get_section_features(
            features, seg["start"], seg["end"]
        )

    # Step 2: Apply direct mappings
    for seg in segments:
        if seg["label"] in DIRECT_MAP:
            seg["label"] = DIRECT_MAP[seg["label"]]

    # Step 3: Classify chorus -> drop, break/bridge -> breakdown
    for seg in segments:
        lbl = seg["original_label"]
        if lbl == "chorus":
            seg["label"] = "drop" if _is_drop(seg["features"], track_stats) else "drop"
        elif lbl in ("break", "bridge"):
            seg["label"] = "breakdown"
        elif lbl in ("inst", "solo"):
            seg["label"] = _classify_by_energy(seg["features"], track_stats)
        elif lbl == "verse":
            seg["label"] = "verse"
        elif lbl in ("start", "end"):
            # Merge artifacts into nearest real section later
            seg["label"] = "intro" if lbl == "start" else "outro"

    # Step 4: Detect builds — rising energy sections before drops
    _detect_builds(segments, track_stats)

    # Step 5: Detect fakeouts — brief energy dips between build and drop
    _detect_fakeouts(segments, track_stats)

    # Clean up internal feature data
    for seg in segments:
        seg.pop("features", None)

    return segments


def _is_drop(section_feat: dict, track_stats: dict) -> bool:
    """Check if a section has drop characteristics."""
    if track_stats["rms_mean"] == 0:
        return False
    energy_ratio = section_feat["rms_mean"] / track_stats["rms_mean"]
    centroid_ratio = section_feat["centroid_mean"] / max(track_stats["centroid_mean"], 1.0)
    return energy_ratio > 1.2 and centroid_ratio < 1.2


def _classify_by_energy(section_feat: dict, track_stats: dict) -> str:
    """Classify an ambiguous section by its energy relative to the track."""
    if track_stats["rms_mean"] == 0:
        return "breakdown"
    energy_ratio = section_feat["rms_mean"] / track_stats["rms_mean"]
    if energy_ratio > 1.3:
        return "drop"
    elif energy_ratio < 0.7:
        return "breakdown"
    else:
        return "verse"


def _detect_builds(segments: list[dict], track_stats: dict) -> None:
    """Find sections with rising energy that precede drops and relabel as 'build'."""
    for i in range(len(segments) - 1):
        seg = segments[i]
        next_seg = segments[i + 1]

        if next_seg["label"] != "drop":
            continue

        feat = seg["features"]

        # Check for rising energy
        has_rising_energy = feat["rms_slope"] > 0
        # Check for rising brightness (risers, noise sweeps)
        has_rising_centroid = feat["centroid_slope"] > 0
        # Not already classified as something definitive
        is_candidate = seg["label"] in ("verse", "breakdown", "intro")

        if is_candidate and has_rising_energy and has_rising_centroid:
            seg["label"] = "build"
        elif is_candidate and has_rising_energy and feat["duration"] < 20:
            # Short section with rising energy before a drop is likely a build
            seg["label"] = "build"


def _detect_fakeouts(segments: list[dict], track_stats: dict) -> None:
    """Find brief energy dips between builds and drops — reclassify as 'fakeout'.

    A fakeout is a short (typically 1-4 bars) moment of silence or minimal
    elements right before the drop hits, creating tension.
    """
    if len(segments) < 3:
        return

    for i in range(1, len(segments) - 1):
        prev = segments[i - 1]
        seg = segments[i]
        next_seg = segments[i + 1]

        # Pattern: build -> ??? -> drop
        if prev["label"] != "build" or next_seg["label"] != "drop":
            continue

        feat = seg["features"]

        # Must be short (< ~8 seconds, roughly 4 bars at 128 BPM)
        is_short = feat["duration"] < 8.0

        # Must have significant energy dip compared to the build
        prev_energy = prev["features"]["rms_mean"]
        if prev_energy > 0:
            energy_dip_ratio = feat["rms_mean"] / prev_energy
            has_energy_dip = energy_dip_ratio < 0.6
        else:
            has_energy_dip = False

        if is_short and has_energy_dip:
            seg["label"] = "fakeout"
