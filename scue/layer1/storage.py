"""Track analysis storage — JSON files (source of truth) + SQLite (derived cache).

JSON files in the project's tracks/ directory are the canonical store.
SQLite in cache/ is a derived index rebuilt from JSON. If the DB is deleted,
nothing is lost — it's rebuilt on next access.

All writes go to JSON first, then update SQLite.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from .models import (
    TrackAnalysis,
    analysis_from_dict,
    analysis_to_dict,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON file storage (source of truth)
# ---------------------------------------------------------------------------

class TrackStore:
    """Manages JSON file storage for track analyses.

    Each analysis is stored as {fingerprint}.json in the tracks/ directory.
    """

    def __init__(self, tracks_dir: str | Path) -> None:
        """Initialize the track store.

        Args:
            tracks_dir: Directory for JSON analysis files.
        """
        self.tracks_dir = Path(tracks_dir)
        self.tracks_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, fingerprint: str, version: int = 1) -> Path:
        """Get the file path for a track analysis."""
        if version == 1:
            return self.tracks_dir / f"{fingerprint}.json"
        return self.tracks_dir / f"{fingerprint}_v{version}.json"

    def save(self, analysis: TrackAnalysis) -> Path:
        """Save a track analysis to JSON.

        Args:
            analysis: The TrackAnalysis to save.

        Returns:
            Path to the saved JSON file.
        """
        path = self._path_for(analysis.fingerprint, analysis.version)
        data = analysis_to_dict(analysis)

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info("Saved analysis: %s (v%d) → %s",
                     analysis.fingerprint[:12], analysis.version, path.name)
        return path

    def load(self, fingerprint: str, version: int = 1) -> TrackAnalysis | None:
        """Load a track analysis from JSON.

        Args:
            fingerprint: Track fingerprint (SHA256).
            version: Analysis version (1=original, 2+=enriched).

        Returns:
            TrackAnalysis or None if not found.
        """
        path = self._path_for(fingerprint, version)
        if not path.exists():
            return None

        with open(path) as f:
            data = json.load(f)

        return analysis_from_dict(data)

    def load_latest(self, fingerprint: str) -> TrackAnalysis | None:
        """Load the latest version of a track analysis.

        Checks for enriched versions first, falls back to v1.
        """
        # Check for versioned files (v2, v3, etc.) in descending order
        for version in range(10, 0, -1):
            result = self.load(fingerprint, version)
            if result is not None:
                return result
        return None

    def exists(self, fingerprint: str) -> bool:
        """Check if an analysis exists for this fingerprint."""
        return self._path_for(fingerprint).exists()

    def list_all(self) -> list[str]:
        """List all fingerprints with stored analyses."""
        fingerprints = []
        for path in self.tracks_dir.glob("*.json"):
            name = path.stem
            # Skip versioned files (contain _v)
            if "_v" not in name:
                fingerprints.append(name)
        return fingerprints

    def delete(self, fingerprint: str) -> None:
        """Delete all versions of a track analysis."""
        for path in self.tracks_dir.glob(f"{fingerprint}*.json"):
            path.unlink()
            logger.info("Deleted: %s", path.name)


# ---------------------------------------------------------------------------
# SQLite cache (derived index)
# ---------------------------------------------------------------------------

class TrackCache:
    """SQLite cache for fast track queries.

    This is a DERIVED cache — the JSON files are the source of truth.
    If the database is deleted, it can be rebuilt from JSON files.
    """

    def __init__(self, db_path: str | Path) -> None:
        """Initialize the SQLite cache.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tracks (
                    fingerprint TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    source TEXT NOT NULL DEFAULT 'analysis',
                    audio_path TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    artist TEXT NOT NULL DEFAULT '',
                    bpm REAL NOT NULL DEFAULT 0.0,
                    duration REAL NOT NULL DEFAULT 0.0,
                    section_count INTEGER NOT NULL DEFAULT 0,
                    mood TEXT NOT NULL DEFAULT 'neutral',
                    key_name TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    PRIMARY KEY (fingerprint, version)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS track_ids (
                    rekordbox_id INTEGER PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    first_seen REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS divergence_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    track_fingerprint TEXT NOT NULL,
                    field TEXT NOT NULL,
                    scue_value TEXT NOT NULL,
                    pioneer_value TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(str(self.db_path))

    def index_analysis(self, analysis: TrackAnalysis) -> None:
        """Add or update a track analysis in the cache.

        Args:
            analysis: The TrackAnalysis to index.
        """
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tracks
                (fingerprint, version, source, audio_path, title, artist,
                 bpm, duration, section_count, mood, key_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                analysis.fingerprint,
                analysis.version,
                analysis.source,
                analysis.audio_path,
                analysis.title,
                analysis.artist,
                analysis.bpm,
                analysis.duration,
                len(analysis.sections),
                analysis.features.mood,
                analysis.features.key,
                analysis.created_at,
            ))

    def list_tracks(
        self,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ) -> list[dict]:
        """List tracks from the cache for table display.

        Returns flattened metadata dicts (not full TrackAnalysis).
        """
        valid_sorts = {"created_at", "title", "artist", "bpm", "duration"}
        if sort_by not in valid_sorts:
            sort_by = "created_at"

        direction = "DESC" if sort_desc else "ASC"

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"""
                SELECT fingerprint, version, source, audio_path, title, artist,
                       bpm, duration, section_count, mood, key_name, created_at
                FROM tracks
                WHERE version = (
                    SELECT MAX(version) FROM tracks t2
                    WHERE t2.fingerprint = tracks.fingerprint
                )
                ORDER BY {sort_by} {direction}
                LIMIT ? OFFSET ?
            """, (limit, offset)).fetchall()

        return [dict(row) for row in rows]

    def get_track(self, fingerprint: str) -> dict | None:
        """Get cached metadata for a single track."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT * FROM tracks
                WHERE fingerprint = ?
                ORDER BY version DESC
                LIMIT 1
            """, (fingerprint,)).fetchone()

        return dict(row) if row else None

    def count_tracks(self) -> int:
        """Count distinct tracks in the cache."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT fingerprint) FROM tracks"
            ).fetchone()
        return row[0] if row else 0

    def rebuild_from_store(self, store: TrackStore) -> int:
        """Rebuild the entire cache from JSON files.

        Args:
            store: TrackStore to read JSON files from.

        Returns:
            Number of tracks indexed.
        """
        logger.info("Rebuilding SQLite cache from JSON files...")

        # Clear existing data
        with self._connect() as conn:
            conn.execute("DELETE FROM tracks")

        count = 0
        for fingerprint in store.list_all():
            analysis = store.load(fingerprint)
            if analysis:
                self.index_analysis(analysis)
                count += 1

        logger.info("Cache rebuilt: %d tracks indexed", count)
        return count
