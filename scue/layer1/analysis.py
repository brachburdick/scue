"""Analysis pipeline orchestrator.

Runs the full offline track analysis pipeline:
1. Compute fingerprint
2. Extract audio features (librosa)
3. Analyze structure (allin1-mlx + fallback)
4. Detect change-point boundaries (ruptures)
5. Merge boundaries
6. Snap to 8-bar grid
7. Classify with EDM flow model
8. Score confidence
9. Compute RGB waveform
10. Store as JSON + index in SQLite

This module coordinates the detectors — it does not contain detection logic.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from .detectors.features import AudioFeatures, extract_all, get_section_features, get_track_stats
from .detectors.flow_model import classify_sections
from .detectors.sections import (
    analyze_structure,
    detect_boundaries,
    merge_boundaries,
)
from .detectors.snap import snap_to_8bar_grid
from .fingerprint import compute_fingerprint
from .models import Section, TrackAnalysis, TrackFeatures
from .storage import TrackCache, TrackStore
from .waveform import compute_rgb_waveform

logger = logging.getLogger(__name__)

# Default ruptures penalty — lower = more change-points
DEFAULT_RUPTURES_PENALTY = 5.0


def run_analysis(
    audio_path: str | Path,
    tracks_dir: str | Path | None = None,
    cache_path: str | Path | None = None,
    ruptures_penalty: float = DEFAULT_RUPTURES_PENALTY,
    skip_waveform: bool = False,
    force: bool = False,
) -> TrackAnalysis:
    """Run the full analysis pipeline on an audio file.

    Args:
        audio_path: Path to the audio file.
        tracks_dir: Directory for JSON storage. If None, no persistence.
        cache_path: Path to SQLite cache. If None, no caching.
        ruptures_penalty: Ruptures penalty parameter.
        skip_waveform: If True, skip RGB waveform computation.
        force: If True, re-analyze even if analysis exists.

    Returns:
        Complete TrackAnalysis object.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    start_time = time.time()
    logger.info("=" * 60)
    logger.info("Starting analysis: %s", audio_path.name)

    # Step 1: Fingerprint
    fingerprint = compute_fingerprint(audio_path)
    logger.info("Fingerprint: %s", fingerprint[:16])

    # Check for existing analysis
    store = TrackStore(tracks_dir) if tracks_dir else None
    if store and not force and store.exists(fingerprint):
        existing = store.load(fingerprint)
        if existing:
            logger.info("Analysis already exists (v%d), skipping. Use force=True to re-analyze.",
                        existing.version)
            return existing

    # Step 2: Extract audio features
    logger.info("Step 2/9: Extracting audio features...")
    features = extract_all(str(audio_path))

    # Step 3: Analyze structure (allin1-mlx or fallback)
    logger.info("Step 3/9: Analyzing structure...")
    structure = analyze_structure(str(audio_path))

    # Step 4: Detect change-point boundaries (ruptures)
    logger.info("Step 4/9: Detecting change-point boundaries...")
    if features.stacked_matrix is None:
        logger.warning("No feature matrix for %s — skipping boundary detection", audio_path.name)
        ruptures_boundaries = []
    else:
        ruptures_boundaries = detect_boundaries(
            features.stacked_matrix,
            features.sr,
            features.hop_length,
            penalty=ruptures_penalty,
        )

    # Step 5: Merge boundaries
    logger.info("Step 5/9: Merging boundaries...")
    merged_sections = merge_boundaries(structure.sections, ruptures_boundaries)

    # Step 6: Snap to 8-bar grid
    logger.info("Step 6/9: Snapping to 8-bar grid...")
    raw_for_snap = [
        {
            "label": s.label,
            "start": s.start,
            "end": s.end,
            "original_label": s.label,
            "confidence": 0.5,
        }
        for s in merged_sections
    ]
    snap_result = snap_to_8bar_grid(
        raw_for_snap,
        structure.downbeats,
        structure.bpm,
    )
    for line in snap_result.snap_report:
        logger.info("  SNAP: %s", line)

    # Step 7: Classify with EDM flow model
    logger.info("Step 7/9: Classifying with EDM flow model...")
    track_stats = get_track_stats(features)
    section_feats = [
        get_section_features(features, s.start, s.end)
        for s in snap_result.sections
    ]
    classified_sections = classify_sections(
        snap_result.sections,
        section_feats,
        track_stats,
    )

    # Step 8: Compute confidence scores
    logger.info("Step 8/9: Scoring confidence...")
    scored_sections = _score_confidence(
        classified_sections,
        structure.source,
    )

    # Clamp section boundaries: first section starts at 0.0, last ends at duration
    if scored_sections:
        first = scored_sections[0]
        scored_sections[0] = Section(
            label=first.label, start=0.0, end=first.end,
            confidence=first.confidence, bar_count=first.bar_count,
            expected_bar_count=first.expected_bar_count,
            irregular_phrase=first.irregular_phrase, fakeout=first.fakeout,
            original_label=first.original_label, source=first.source,
        )
        last = scored_sections[-1]
        scored_sections[-1] = Section(
            label=last.label, start=last.start, end=features.duration,
            confidence=last.confidence, bar_count=last.bar_count,
            expected_bar_count=last.expected_bar_count,
            irregular_phrase=last.irregular_phrase, fakeout=last.fakeout,
            original_label=last.original_label, source=last.source,
        )

    # Step 8.5: Event detection (M7)
    logger.info("Step 8.5: Detecting musical events...")
    detected_events, drum_patterns = _run_event_detection(
        features, structure.beats, structure.downbeats, scored_sections,
    )

    # Step 9: Compute RGB waveform
    waveform = None
    if not skip_waveform:
        logger.info("Step 9/9: Computing RGB waveform...")
        waveform = compute_rgb_waveform(features.signal, features.sr)
    else:
        logger.info("Step 9/9: Skipping waveform (skip_waveform=True)")

    # Extract title from filename
    title = audio_path.stem

    # Build energy curve (downsampled RMS)
    energy_curve = features.rms[::4].tolist() if features.rms is not None else []

    # Build TrackAnalysis
    analysis = TrackAnalysis(
        fingerprint=fingerprint,
        audio_path=str(audio_path),
        title=title,
        bpm=structure.bpm,
        beats=structure.beats,
        downbeats=structure.downbeats,
        beatgrid_source="analysis",
        sections=scored_sections,
        events=detected_events,
        drum_patterns=drum_patterns,
        features=TrackFeatures(
            energy_curve=energy_curve,
            mood="neutral",  # Tier 3 — future
            danceability=0.5,
        ),
        waveform=waveform,
        version=1,
        source="analysis",
        created_at=time.time(),
        duration=features.duration,
    )

    # Persist
    if store:
        store.save(analysis)

    if cache_path:
        cache = TrackCache(cache_path)
        cache.index_analysis(analysis)

    elapsed = time.time() - start_time
    logger.info("Analysis complete in %.1fs: %d sections, BPM=%.1f, duration=%.1fs",
                elapsed, len(scored_sections), structure.bpm, features.duration)
    logger.info("=" * 60)

    return analysis


def _score_confidence(
    sections: list[Section],
    structure_source: str,
) -> list[Section]:
    """Adjust confidence based on agreement between detection methods.

    - Both allin1 + ruptures agree on boundary: 0.95
    - allin1 only: 0.7 (weighted by flow model score)
    - ruptures only: 0.5
    - Neither (fallback): 0.3
    """
    result: list[Section] = []

    for section in sections:
        if structure_source == "allin1":
            # allin1 was available — use flow model confidence as base
            # and boost slightly for having ML backing
            base_conf = section.confidence
            conf = min(1.0, base_conf * 1.1)
        else:
            # Fallback mode — lower confidence across the board
            conf = max(0.3, section.confidence * 0.7)

        result.append(Section(
            label=section.label,
            start=section.start,
            end=section.end,
            confidence=round(conf, 3),
            bar_count=section.bar_count,
            expected_bar_count=section.expected_bar_count,
            irregular_phrase=section.irregular_phrase,
            fakeout=section.fakeout,
            original_label=section.original_label,
            source=section.source,
        ))

    return result


def _run_event_detection(
    features: AudioFeatures,
    beats: list[float],
    downbeats: list[float],
    sections: list[Section],
) -> tuple[list, list]:
    """Run configured event detectors and merge results.

    Returns:
        Tuple of (tonal_events: list[MusicalEvent], drum_patterns: list[DrumPattern]).
    """
    from .detectors.events import DetectorResult, DrumPattern, load_detector_config
    from .models import MusicalEvent

    try:
        config = load_detector_config()
    except Exception:
        logger.exception("Failed to load detector config — skipping event detection")
        return [], []

    all_events: list[MusicalEvent] = []
    all_patterns: list[DrumPattern] = []
    active = config.active_strategies

    # Percussion detection
    perc_strategy = active.get("percussion")
    if perc_strategy:
        try:
            if perc_strategy == "random_forest":
                from .detectors.percussion_rf import PercussionRFDetector
                detector = PercussionRFDetector()
            else:
                from .detectors.percussion_heuristic import PercussionHeuristicDetector
                detector = PercussionHeuristicDetector()

            result = detector.detect(features, beats, downbeats, sections, config)
            all_patterns.extend(result.patterns)
            all_events.extend(result.events)
            logger.info("Percussion (%s): %d patterns", perc_strategy, len(result.patterns))
        except Exception:
            logger.exception("Percussion detection failed (strategy=%s)", perc_strategy)

    # Riser detection
    if active.get("riser"):
        try:
            from .detectors.tonal import RiserDetector
            result = RiserDetector().detect(features, beats, downbeats, sections, config)
            all_events.extend(result.events)
            logger.info("Riser detection: %d events", len(result.events))
        except Exception:
            logger.exception("Riser detection failed")

    # Faller detection
    if active.get("faller"):
        try:
            from .detectors.tonal import FallerDetector
            result = FallerDetector().detect(features, beats, downbeats, sections, config)
            all_events.extend(result.events)
            logger.info("Faller detection: %d events", len(result.events))
        except Exception:
            logger.exception("Faller detection failed")

    # Stab detection
    if active.get("stab"):
        try:
            from .detectors.tonal import StabDetector
            result = StabDetector().detect(features, beats, downbeats, sections, config)
            all_events.extend(result.events)
            logger.info("Stab detection: %d events", len(result.events))
        except Exception:
            logger.exception("Stab detection failed")

    # Sort all events by timestamp
    all_events.sort(key=lambda e: e.timestamp)

    logger.info(
        "Event detection complete: %d events, %d drum patterns",
        len(all_events), len(all_patterns),
    )
    return all_events, all_patterns
