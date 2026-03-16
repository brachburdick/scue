"""DivergenceRecord logging — Layer 1.

Every time SCUE's analysis differs from Pioneer/rekordbox data, a DivergenceRecord
is written here. Over time, patterns in the log reveal systematic biases in SCUE's
detectors (e.g., "drop boundaries consistently placed 1 beat early").
"""

import logging
from typing import Any

from .models import DivergenceRecord
from .storage import TrackCache

log = logging.getLogger(__name__)


def log_divergence(
    cache: TrackCache,
    track_fingerprint: str,
    divergence_field: str,
    scue_value: Any,
    pioneer_value: Any,
    resolution: str = "pioneer_adopted",
) -> DivergenceRecord:
    """Create and persist a DivergenceRecord to the SQLite cache.

    Args:
        cache: TrackCache instance for persistence.
        track_fingerprint: SHA256 of the audio file.
        divergence_field: which field diverges ("beatgrid", "bpm", "key", etc.)
        scue_value: what SCUE computed.
        pioneer_value: what Pioneer/rekordbox reported.
        resolution: "pioneer_adopted" | "scue_kept" | "manual_override".
    """
    record = DivergenceRecord(
        track_fingerprint=track_fingerprint,
        divergence_field=divergence_field,
        scue_value=str(scue_value),
        pioneer_value=str(pioneer_value),
        resolution=resolution,
    )
    cache.store_divergence(record)
    log.info(
        "Divergence: fp=%s field=%s scue=%s pioneer=%s → %s",
        track_fingerprint[:12], divergence_field, scue_value, pioneer_value, resolution,
    )
    return record


def query_divergences(
    cache: TrackCache,
    track_fingerprint: str | None = None,
    divergence_field: str | None = None,
) -> list[DivergenceRecord]:
    """Query logged divergences from the SQLite cache, optionally filtered."""
    return cache.query_divergences(
        track_fingerprint=track_fingerprint,
        divergence_field=divergence_field,
    )
