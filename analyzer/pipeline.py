"""Main analysis pipeline orchestrator.

Coordinates feature extraction, ML structure analysis, change-point
detection, boundary merging, EDM classification, quantization,
and confidence scoring.
"""

import numpy as np
from . import features as feat_mod
from .structure import analyze_structure
from .changepoint import detect_boundaries
from .edm_classifier import classify_sections
from .waveform import compute_rgb_waveform


BOUNDARY_TOLERANCE_SEC = 2.0  # allin1 & ruptures boundaries within this are "matching"


def run_analysis(audio_path: str, ruptures_penalty: float = 5.0) -> dict:
    """Run the full analysis pipeline on an audio file.

    Returns a JSON-serializable dict with sections, BPM, beats,
    downbeats, energy profile, and RGB waveform data.
    """
    # Step 1: Extract librosa features
    features = feat_mod.extract_all(audio_path)

    # Step 2: ML structure analysis
    structure = analyze_structure(audio_path)

    # Step 3: Change-point detection
    ruptures_boundaries = detect_boundaries(
        features["stacked_matrix"],
        features["sr"],
        features["hop_length"],
        penalty=ruptures_penalty,
    )

    # Step 4: Merge boundaries
    segments = _merge_boundaries(
        structure["segments"],
        ruptures_boundaries,
        structure["downbeats"],
        features,
    )

    # Step 5: EDM classification
    segments = classify_sections(segments, features)

    # Step 6: Quantize to downbeats
    segments = _quantize_to_downbeats(segments, structure["downbeats"])

    # Step 7: Confidence scoring
    segments = _score_confidence(
        segments, structure["segments"], ruptures_boundaries
    )

    # Step 8: RGB waveform
    waveform_data = compute_rgb_waveform(features["signal"], features["sr"])

    # Step 9: Energy profile (downsampled RMS for the frontend)
    energy_profile = features["rms"][::4].tolist()

    return {
        "bpm": structure["bpm"],
        "beats": structure["beats"],
        "downbeats": structure["downbeats"],
        "sections": [
            {
                "label": s["label"],
                "start": round(s["start"], 3),
                "end": round(s["end"], 3),
                "confidence": round(s.get("confidence", 0.5), 2),
            }
            for s in segments
        ],
        "energy_profile": [round(float(e), 4) for e in energy_profile],
        "waveform": waveform_data,
    }


def _merge_boundaries(
    allin1_segments: list[dict],
    ruptures_boundaries: list[float],
    downbeats: list[float],
    features: dict,
) -> list[dict]:
    """Merge allin1 segments with ruptures-detected boundaries.

    allin1 segments are the primary structure. Ruptures boundaries that
    don't correspond to an existing segment boundary may split long segments.
    """
    # Start with allin1 segments as-is
    segments = [dict(s) for s in allin1_segments]

    if not segments:
        return segments

    # Collect existing boundary times
    existing_boundaries = set()
    for seg in segments:
        existing_boundaries.add(seg["start"])
        existing_boundaries.add(seg["end"])

    # Check each ruptures boundary
    min_split_duration = 6.0  # only split segments longer than this

    for rb in ruptures_boundaries:
        # Skip if it matches an existing boundary
        if any(abs(rb - eb) < BOUNDARY_TOLERANCE_SEC for eb in existing_boundaries):
            continue

        # Find which segment this falls within
        for i, seg in enumerate(segments):
            if seg["start"] + min_split_duration < rb < seg["end"] - min_split_duration:
                # Split the segment
                new_seg = {
                    "label": seg["label"],
                    "start": rb,
                    "end": seg["end"],
                }
                seg["end"] = rb
                segments.insert(i + 1, new_seg)
                existing_boundaries.add(rb)
                break

    return segments


def _quantize_to_downbeats(
    segments: list[dict], downbeats: list[float]
) -> list[dict]:
    """Snap segment boundaries to nearest downbeats."""
    if not downbeats:
        return segments

    db = np.array(downbeats)

    for seg in segments:
        seg["start"] = float(_nearest(db, seg["start"]))
        seg["end"] = float(_nearest(db, seg["end"]))

    # Ensure no gaps or overlaps
    for i in range(len(segments) - 1):
        segments[i]["end"] = segments[i + 1]["start"]

    # Fix first and last
    if segments:
        segments[0]["start"] = 0.0
        # Keep last segment's end as-is (track end)

    return segments


def _nearest(arr: np.ndarray, value: float) -> float:
    idx = np.argmin(np.abs(arr - value))
    return float(arr[idx])


def _score_confidence(
    segments: list[dict],
    allin1_segments: list[dict],
    ruptures_boundaries: list[float],
) -> list[dict]:
    """Score each section boundary based on agreement between methods."""
    allin1_bounds = set()
    for seg in allin1_segments:
        allin1_bounds.add(seg["start"])
        allin1_bounds.add(seg["end"])

    rb_set = set(ruptures_boundaries)

    for seg in segments:
        start_conf = _boundary_confidence(seg["start"], allin1_bounds, rb_set)
        end_conf = _boundary_confidence(seg["end"], allin1_bounds, rb_set)
        seg["confidence"] = (start_conf + end_conf) / 2.0

    return segments


def _boundary_confidence(
    time: float, allin1_bounds: set, ruptures_bounds: set
) -> float:
    """Score a single boundary time based on method agreement."""
    has_allin1 = any(abs(time - b) < BOUNDARY_TOLERANCE_SEC for b in allin1_bounds)
    has_ruptures = any(abs(time - b) < BOUNDARY_TOLERANCE_SEC for b in ruptures_bounds)

    if has_allin1 and has_ruptures:
        return 0.95
    elif has_allin1:
        return 0.7
    elif has_ruptures:
        return 0.5
    else:
        return 0.3
