"""Re-analysis pass — re-runs downstream analysis using Pioneer beatgrid.

Unlike the enrichment pass (which only rescales/snaps timestamps), this module
re-runs the actual analytical steps with the Pioneer beatgrid as the timing
reference:

  1. Re-snap section boundaries to the Pioneer downbeat grid (8-bar grid pass)
  2. Re-classify sections with the EDM flow model
  3. Re-score confidence
  4. Re-detect events (M7 detectors) using Pioneer beats/downbeats

This produces a new TrackAnalysis version (source="pioneer_reanalyzed") stored
alongside the original (v1) and enriched (v2) versions. No data is overwritten.

Requires:
  - An enriched TrackAnalysis (v2+, source="pioneer_enriched") with Pioneer beatgrid
  - The original audio file (needed to compute AudioFeatures for event detection)
"""

from __future__ import annotations

import copy
import logging
import time
from pathlib import Path

from .analysis import run_event_detection, score_confidence
from .detectors.features import extract_all, get_section_features, get_track_stats
from .detectors.flow_model import classify_sections
from .detectors.snap import snap_to_8bar_grid
from .models import Section, TrackAnalysis
from .storage import TrackCache, TrackStore

log = logging.getLogger(__name__)


def run_reanalysis_pass(
    enriched: TrackAnalysis,
    audio_path: Path,
    store: TrackStore,
    cache: TrackCache,
) -> TrackAnalysis:
    """Re-run downstream analysis using the Pioneer beatgrid.

    Takes an enriched TrackAnalysis (with Pioneer beats/downbeats already
    adopted) and re-runs section snapping, classification, confidence
    scoring, and event detection. The result is stored as a new version.

    Args:
        enriched: TrackAnalysis with source="pioneer_enriched" and Pioneer
                  beatgrid in beats/downbeats fields.
        audio_path: Path to the audio file (needed for AudioFeatures).
        store: TrackStore for persisting the reanalyzed version.
        cache: TrackCache for indexing.

    Returns:
        A new TrackAnalysis with version incremented and
        source="pioneer_reanalyzed". The enriched analysis is not modified.

    Raises:
        ValueError: If the enriched analysis has no Pioneer beatgrid.
        FileNotFoundError: If the audio file does not exist.
    """
    if not enriched.pioneer_beatgrid and enriched.beatgrid_source != "pioneer_enriched":
        raise ValueError(
            "Reanalysis requires an enriched analysis with Pioneer beatgrid. "
            f"Got source={enriched.source!r}, beatgrid_source={enriched.beatgrid_source!r}"
        )

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    start_time = time.time()
    log.info(
        "Re-analysis starting: fp=%s v%d audio=%s",
        enriched.fingerprint[:12], enriched.version, audio_path.name,
    )

    # ── Set up the new version ────────────────────────────────────────
    reanalyzed = copy.deepcopy(enriched)
    reanalyzed.version = enriched.version + 1
    reanalyzed.source = "pioneer_reanalyzed"
    reanalyzed.enrichment_timestamp = time.time()

    # ── Step 1: Extract audio features ────────────────────────────────
    # This is the expensive step (~5-10s). Features are needed for section
    # classification and event detection.
    log.info("  Step 1: Extracting audio features...")
    features = extract_all(str(audio_path))

    # ── Step 2: Re-snap sections to Pioneer downbeat grid ─────────────
    log.info("  Step 2: Re-snapping sections to Pioneer grid...")
    raw_sections = [
        {
            "label": s.original_label or s.label,
            "start": s.start,
            "end": s.end,
            "original_label": s.original_label or s.label,
            "confidence": s.confidence,
        }
        for s in enriched.sections
    ]
    snap_result = snap_to_8bar_grid(
        raw_sections,
        reanalyzed.downbeats,
        reanalyzed.bpm,
    )
    for line in snap_result.snap_report:
        log.info("  SNAP: %s", line)

    # ── Step 3: Re-classify with EDM flow model ──────────────────────
    log.info("  Step 3: Re-classifying sections...")
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

    # ── Step 4: Re-score confidence ──────────────────────────────────
    log.info("  Step 4: Re-scoring confidence...")
    scored_sections = score_confidence(
        classified_sections,
        "pioneer_reanalyzed",
    )

    # ── Clamp section boundaries ─────────────────────────────────────
    if scored_sections:
        first = scored_sections[0]
        scored_sections[0] = Section(
            label=first.label, start=0.0, end=first.end,
            confidence=first.confidence, bar_count=first.bar_count,
            expected_bar_count=first.expected_bar_count,
            irregular_phrase=first.irregular_phrase, fakeout=first.fakeout,
            original_label=first.original_label,
            source="pioneer_reanalyzed",
        )
        last = scored_sections[-1]
        scored_sections[-1] = Section(
            label=last.label, start=last.start, end=reanalyzed.duration,
            confidence=last.confidence, bar_count=last.bar_count,
            expected_bar_count=last.expected_bar_count,
            irregular_phrase=last.irregular_phrase, fakeout=last.fakeout,
            original_label=last.original_label,
            source="pioneer_reanalyzed",
        )

    reanalyzed.sections = scored_sections

    # ── Step 5: Re-detect events with Pioneer grid ───────────────────
    log.info("  Step 5: Re-detecting events with Pioneer beats/downbeats...")
    detected_events, drum_patterns = run_event_detection(
        features,
        reanalyzed.beats,
        reanalyzed.downbeats,
        scored_sections,
    )
    reanalyzed.events = detected_events
    reanalyzed.drum_patterns = drum_patterns

    # ── Persist ──────────────────────────────────────────────────────
    store.save(reanalyzed)
    cache.index_analysis(reanalyzed)

    elapsed = time.time() - start_time
    log.info(
        "Re-analysis complete: fp=%s v%d→v%d "
        "%d sections, %d events, %d patterns, %.1fs",
        enriched.fingerprint[:12],
        enriched.version, reanalyzed.version,
        len(scored_sections), len(detected_events), len(drum_patterns),
        elapsed,
    )
    return reanalyzed
