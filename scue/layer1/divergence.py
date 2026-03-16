"""DivergenceRecord logging — Layer 1.

Every time SCUE's analysis differs from Pioneer/rekordbox data, a DivergenceRecord
is written here. Over time, patterns in the log reveal systematic biases in SCUE's
detectors (e.g., "drop boundaries consistently placed 1 beat early").
"""

import logging
from pathlib import Path
from typing import Any

from .models import DivergenceRecord
from . import db as _db

log = logging.getLogger(__name__)


def log_divergence(
    track_fingerprint: str,
    field: str,
    scue_value: Any,
    pioneer_value: Any,
    resolution: str = "pioneer_adopted",
    db_path: Path = _db.DB_PATH,
) -> DivergenceRecord:
    """Create and persist a DivergenceRecord to SQLite.

    Args:
        track_fingerprint: SHA256 of the audio file
        field: which field diverges ("beatgrid", "bpm", "key", "section_boundary", "section_label")
        scue_value: what SCUE computed
        pioneer_value: what Pioneer/rekordbox reported
        resolution: "pioneer_adopted" | "scue_kept" | "manual_override"
        db_path: database path (default: standard location)
    """
    record = DivergenceRecord(
        track_fingerprint=track_fingerprint,
        field=field,
        scue_value=scue_value,
        pioneer_value=pioneer_value,
        resolution=resolution,
    )
    _db.store_divergence(
        track_fingerprint=track_fingerprint,
        field=field,
        scue_value=str(scue_value),
        pioneer_value=str(pioneer_value),
        resolution=resolution,
        timestamp=record.timestamp,
        db_path=db_path,
    )
    log.info(
        "Divergence: fp=%s field=%s scue=%s pioneer=%s → %s",
        track_fingerprint[:12], field, scue_value, pioneer_value, resolution,
    )
    return record


def query_divergences(
    track_fingerprint: str | None = None,
    field: str | None = None,
    db_path: Path = _db.DB_PATH,
) -> list[DivergenceRecord]:
    """Query logged divergences from SQLite, optionally filtered."""
    rows = _db.query_divergences_db(
        track_fingerprint=track_fingerprint,
        field=field,
        db_path=db_path,
    )
    return [
        DivergenceRecord(
            track_fingerprint=r["track_fingerprint"],
            field=r["field"],
            scue_value=r["scue_value"],
            pioneer_value=r["pioneer_value"],
            resolution=r["resolution"],
            timestamp=r["timestamp"],
        )
        for r in rows
    ]
