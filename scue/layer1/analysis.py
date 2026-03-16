"""Offline analysis pipeline orchestrator — Layer 1A.

Coordinates the sequential analysis stages:
  1. librosa feature extraction (detectors/features.py)
  2. ML structure analysis — allin1-mlx (detectors/sections.py)
  3. Ruptures change-point detection (detectors/sections.py)
  4. Boundary merging
  5. EDM flow model labeling (detectors/flow_model.py)
  6. Downbeat quantization
  7. Confidence scoring
  8. RGB waveform data (waveform.py)

TODO(milestone-1): add 8-bar snapping pass between steps 4 and 5.
TODO(milestone-1): add SQLite storage via db.py (run_analysis currently returns dict only).
TODO(milestone-7): add Tier 2 event detection (percussion, melodic, effect sweeps).
"""

import logging

import numpy as np

from .detectors import features as feat_mod
from .detectors.sections import analyze_structure, detect_boundaries
from .detectors.flow_model import classify_sections
from .waveform import compute_rgb_waveform
from .models import TrackAnalysis, Section, TrackFeatures
from . import db as _db

log = logging.getLogger(__name__)


BOUNDARY_TOLERANCE_SEC = 2.0  # allin1 & ruptures boundaries within this are "matching"


def run_analysis(audio_path: str, ruptures_penalty: float = 5.0) -> dict:
    """Run the full Tier 1 analysis pipeline on an audio file.

    Returns a JSON-serializable dict with sections, BPM, beats,
    downbeats, energy profile, and RGB waveform data.

    This is the entry point called by the FastAPI server at /api/analyze/{track_id}.
    """
    # Stage 1: Extract librosa features
    features = feat_mod.extract_all(audio_path)

    # Stage 2: ML structure analysis (allin1-mlx)
    structure = analyze_structure(audio_path)

    # Stage 3: Ruptures change-point detection (secondary boundaries)
    ruptures_boundaries = detect_boundaries(
        features["stacked_matrix"],
        features["sr"],
        features["hop_length"],
        penalty=ruptures_penalty,
    )

    # Stage 4: Merge boundaries (allin1 primary, ruptures splits long sections)
    segments = _merge_boundaries(
        structure["segments"],
        ruptures_boundaries,
        structure["downbeats"],
        features,
    )

    # TODO(milestone-1): Stage 4b — 8-bar snapping pass
    # segments = snap_to_8bar_grid(segments, structure["downbeats"])

    # Stage 5: EDM flow model labeling
    segments = classify_sections(segments, features)

    # Stage 6: Quantize to downbeats
    segments = _quantize_to_downbeats(segments, structure["downbeats"])

    # Stage 7: Confidence scoring
    segments = _score_confidence(
        segments, structure["segments"], ruptures_boundaries
    )

    # Stage 8: RGB waveform (for frontend visualization)
    waveform_data = compute_rgb_waveform(features["signal"], features["sr"])

    # Stage 9: Energy profile (downsampled RMS for the frontend)
    energy_profile = features["rms"][::4].tolist()

    # ── Persist to SQLite ────────────────────────────────────────────
    fp = _db.fingerprint(audio_path)

    # Check if analysis already exists (avoid re-storing duplicates)
    existing = _db.load_analysis(fp, version=1)
    if existing is None:
        section_objs = [
            Section(
                label=s["label"],
                start=round(s["start"], 3),
                end=round(s["end"], 3),
                confidence=round(s.get("confidence", 0.5), 2),
                original_label=s.get("original_label", s["label"]),
            )
            for s in segments
        ]
        track_analysis = TrackAnalysis(
            fingerprint=fp,
            audio_path=audio_path,
            bpm=structure["bpm"],
            beats=structure["beats"],
            downbeats=structure["downbeats"],
            sections=section_objs,
            features=TrackFeatures(
                energy_curve=[round(float(e), 4) for e in energy_profile],
            ),
        )
        _db.store_analysis(track_analysis)
        log.info("Persisted analysis for fp=%s", fp[:12])

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
    segments = [dict(s) for s in allin1_segments]

    if not segments:
        return segments

    existing_boundaries = set()
    for seg in segments:
        existing_boundaries.add(seg["start"])
        existing_boundaries.add(seg["end"])

    min_split_duration = 6.0  # only split segments longer than this

    for rb in ruptures_boundaries:
        if any(abs(rb - eb) < BOUNDARY_TOLERANCE_SEC for eb in existing_boundaries):
            continue

        for i, seg in enumerate(segments):
            if seg["start"] + min_split_duration < rb < seg["end"] - min_split_duration:
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

    for i in range(len(segments) - 1):
        segments[i]["end"] = segments[i + 1]["start"]

    if segments:
        segments[0]["start"] = 0.0

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
