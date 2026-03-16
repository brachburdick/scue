"""Pioneer enrichment pass — Layer 1B.

When a track is first loaded on Pioneer hardware, SCUE receives Pioneer/rekordbox
metadata (beatgrid, BPM, key). This module uses that data to refine the offline
TrackAnalysis:

  1. Replace the librosa beatgrid with the Pioneer beatgrid
  2. Use Pioneer's BPM as the authoritative base BPM
  3. Use Pioneer's key detection as the reference key
  4. Re-align all section boundaries and Tier 2 event timestamps to the Pioneer grid
  5. Store the updated analysis as a new versioned entry in the database
  6. Log a DivergenceRecord for every field that differed

The original "analysis" version is NEVER overwritten — the enriched version
is stored alongside it, tagged source="pioneer_enriched".
"""

import bisect
import copy
import logging
from pathlib import Path

from .models import TrackAnalysis, Section, MusicalEvent, TrackFeatures
from .divergence import log_divergence
from . import db as _db

log = logging.getLogger(__name__)


def _snap_time_to_grid(t: float, beatgrid: list[float]) -> float:
    """Snap a timestamp to the nearest beat in the given beatgrid."""
    if not beatgrid:
        return t
    idx = bisect.bisect_left(beatgrid, t)
    candidates = []
    if idx > 0:
        candidates.append(beatgrid[idx - 1])
    if idx < len(beatgrid):
        candidates.append(beatgrid[idx])
    return min(candidates, key=lambda b: abs(b - t))


def _compute_downbeats(beatgrid: list[float], bpm: float) -> list[float]:
    """Extract downbeats (every 4th beat) from a beatgrid."""
    if not beatgrid:
        return []
    return beatgrid[::4]


def run_enrichment_pass(
    analysis: TrackAnalysis,
    pioneer_bpm: float,
    pioneer_beatgrid: list[float] | None = None,
    pioneer_key: str = "",
    pioneer_phrase_data: list[dict] | None = None,
    db_path: Path = _db.DB_PATH,
) -> TrackAnalysis:
    """Enrich a TrackAnalysis with Pioneer/rekordbox metadata.

    Args:
        analysis: the existing TrackAnalysis (source="analysis")
        pioneer_bpm: BPM reported by Pioneer hardware
        pioneer_beatgrid: beat timestamps from the Pioneer/rekordbox beatgrid (or None)
        pioneer_key: key string from Pioneer (e.g. "Am", "F#"), empty if unavailable
        pioneer_phrase_data: rekordbox phrase labels if available, or None
        db_path: database path for divergence logging

    Returns:
        A new TrackAnalysis with version incremented and source="pioneer_enriched".
        The original analysis is not modified.
    """
    enriched = copy.deepcopy(analysis)
    enriched.version = analysis.version + 1
    enriched.beatgrid_source = "pioneer_enriched"

    # ── BPM enrichment ───────────────────────────────────────────────
    bpm_ratio = 1.0
    if pioneer_bpm > 0 and abs(pioneer_bpm - analysis.bpm) > 0.05:
        log_divergence(
            analysis.fingerprint, "bpm",
            analysis.bpm, pioneer_bpm,
            resolution="pioneer_adopted",
            db_path=db_path,
        )
        bpm_ratio = pioneer_bpm / analysis.bpm
        enriched.bpm = pioneer_bpm
        log.info("BPM enrichment: %.2f → %.2f (ratio %.4f)", analysis.bpm, pioneer_bpm, bpm_ratio)

    # ── Beatgrid enrichment ──────────────────────────────────────────
    if pioneer_beatgrid:
        if analysis.beats:
            log_divergence(
                analysis.fingerprint, "beatgrid",
                f"{len(analysis.beats)} beats",
                f"{len(pioneer_beatgrid)} beats",
                resolution="pioneer_adopted",
                db_path=db_path,
            )
        enriched.beats = list(pioneer_beatgrid)
        enriched.downbeats = _compute_downbeats(pioneer_beatgrid, enriched.bpm)
    elif bpm_ratio != 1.0:
        # No Pioneer beatgrid available — scale existing timestamps by BPM ratio
        enriched.beats = [t / bpm_ratio for t in analysis.beats]
        enriched.downbeats = [t / bpm_ratio for t in analysis.downbeats]

    # ── Key enrichment ───────────────────────────────────────────────
    if pioneer_key and pioneer_key != analysis.features.key:
        if analysis.features.key:
            log_divergence(
                analysis.fingerprint, "key",
                analysis.features.key, pioneer_key,
                resolution="pioneer_adopted",
                db_path=db_path,
            )
        enriched.features.key = pioneer_key
        enriched.features.key_source = "pioneer_enriched"

    # ── Section timestamp scaling ────────────────────────────────────
    target_grid = enriched.beats if pioneer_beatgrid else None
    for section in enriched.sections:
        if bpm_ratio != 1.0:
            section.start /= bpm_ratio
            section.end /= bpm_ratio
        # Snap to Pioneer beatgrid if available
        if target_grid:
            section.start = _snap_time_to_grid(section.start, target_grid)
            section.end = _snap_time_to_grid(section.end, target_grid)
        section.source = "pioneer_enriched"

    # ── Event timestamp scaling ──────────────────────────────────────
    for event in enriched.events:
        if bpm_ratio != 1.0:
            event.timestamp /= bpm_ratio
            if event.duration is not None:
                event.duration /= bpm_ratio

    # ── Energy curve scaling (downsample positions shift with BPM) ───
    # Energy curve is position-indexed, not time-indexed, so no scaling needed.

    log.info(
        "Enrichment complete: fp=%s v%d→v%d bpm_ratio=%.4f beatgrid=%s key=%s",
        analysis.fingerprint[:12],
        analysis.version, enriched.version,
        bpm_ratio,
        "pioneer" if pioneer_beatgrid else "scaled",
        pioneer_key or "(unchanged)",
    )
    return enriched
