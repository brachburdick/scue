"""SQLite storage for TrackAnalysis objects — Layer 1A.

Keyed by SHA256 track fingerprint. Supports versioned analyses
(pre- and post-Pioneer enrichment stored separately).

Status: STUB — not yet implemented (Milestone 1).
"""

import hashlib
import sqlite3
from pathlib import Path
from typing import Optional

from .models import TrackAnalysis

# Default database location
DB_PATH = Path(__file__).parent.parent.parent / "data" / "scue.db"


def fingerprint(audio_path: str) -> str:
    """Compute SHA256 fingerprint of an audio file.

    This is the primary key for all stored analyses.
    """
    h = hashlib.sha256()
    with open(audio_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def store_analysis(analysis: TrackAnalysis, db_path: Path = DB_PATH) -> None:
    """Persist a TrackAnalysis to the database.

    TODO(milestone-1): implement schema and serialization.
    """
    # TODO: implement
    raise NotImplementedError("db.store_analysis not yet implemented — see Milestone 1")


def load_analysis(
    fp: str,
    version: Optional[int] = None,
    db_path: Path = DB_PATH,
) -> Optional[TrackAnalysis]:
    """Load a TrackAnalysis by fingerprint.

    Args:
        fp: SHA256 fingerprint
        version: specific version to load, or None for latest

    Returns:
        TrackAnalysis or None if not found.

    TODO(milestone-1): implement.
    """
    # TODO: implement
    return None


def list_tracks(db_path: Path = DB_PATH) -> list[dict]:
    """Return summary info for all stored tracks.

    TODO(milestone-1): implement.
    """
    # TODO: implement
    return []
