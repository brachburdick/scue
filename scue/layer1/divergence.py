"""DivergenceRecord logging — Layer 1.

Every time SCUE's analysis differs from Pioneer/rekordbox data, a DivergenceRecord
is written here. Over time, patterns in the log reveal systematic biases in SCUE's
detectors (e.g., "drop boundaries consistently placed 1 beat early").

Status: STUB — not yet implemented (Milestone 2).
"""

from typing import Any
from .models import DivergenceRecord


def log_divergence(
    track_fingerprint: str,
    field: str,
    scue_value: Any,
    pioneer_value: Any,
    resolution: str = "pioneer_adopted",
) -> DivergenceRecord:
    """Create and persist a DivergenceRecord.

    Args:
        track_fingerprint: SHA256 of the audio file
        field: which field diverges ("beatgrid", "bpm", "key", "section_boundary", "section_label")
        scue_value: what SCUE computed
        pioneer_value: what Pioneer/rekordbox reported
        resolution: "pioneer_adopted" | "scue_kept" | "manual_override"

    TODO(milestone-2): persist to SQLite via db.py.
    """
    record = DivergenceRecord(
        track_fingerprint=track_fingerprint,
        field=field,
        scue_value=scue_value,
        pioneer_value=pioneer_value,
        resolution=resolution,
    )
    # TODO: persist to database
    return record


def query_divergences(
    track_fingerprint: str | None = None,
    field: str | None = None,
) -> list[DivergenceRecord]:
    """Query logged divergences, optionally filtered by track or field.

    TODO(milestone-2): implement database query.
    """
    # TODO: implement
    return []
