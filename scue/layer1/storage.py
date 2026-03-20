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
    DivergenceRecord,
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
# Schema migration helpers (DROP + recreate for derived cache tables)
# ---------------------------------------------------------------------------

def _migrate_track_ids(conn: sqlite3.Connection) -> None:
    """Drop old single-column-PK track_ids table if it exists.

    Data loss is acceptable — USB rescan repopulates.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='track_ids'"
    ).fetchone()
    if row and "source_player" not in row[0]:
        logger.info("Migrating track_ids table: dropping old single-PK schema")
        conn.execute("DROP TABLE track_ids")


def _migrate_pioneer_metadata(conn: sqlite3.Connection) -> None:
    """Drop old single-column-PK pioneer_metadata table if it exists.

    Data loss is acceptable — USB rescan repopulates.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='pioneer_metadata'"
    ).fetchone()
    if row and "source_player" not in row[0]:
        logger.info("Migrating pioneer_metadata table: dropping old single-PK schema")
        conn.execute("DROP TABLE pioneer_metadata")


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
            # Migration: drop old single-column-PK track_ids if it exists
            _migrate_track_ids(conn)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS track_ids (
                    source_player TEXT NOT NULL,
                    source_slot TEXT NOT NULL,
                    rekordbox_id INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL,
                    first_seen REAL NOT NULL,
                    PRIMARY KEY (source_player, source_slot, rekordbox_id)
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
            # Migration: drop old single-column-PK pioneer_metadata if it exists
            _migrate_pioneer_metadata(conn)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pioneer_metadata (
                    source_player TEXT NOT NULL,
                    source_slot TEXT NOT NULL,
                    rekordbox_id INTEGER NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    artist TEXT NOT NULL DEFAULT '',
                    bpm REAL NOT NULL DEFAULT 0.0,
                    key_name TEXT NOT NULL DEFAULT '',
                    beatgrid_json TEXT NOT NULL DEFAULT '[]',
                    cue_points_json TEXT NOT NULL DEFAULT '[]',
                    memory_points_json TEXT NOT NULL DEFAULT '[]',
                    hot_cues_json TEXT NOT NULL DEFAULT '[]',
                    file_path TEXT NOT NULL DEFAULT '',
                    scan_timestamp REAL NOT NULL,
                    PRIMARY KEY (source_player, source_slot, rekordbox_id)
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

    def lookup_fingerprint(
        self,
        rekordbox_id: int,
        source_player: str = "1",
        source_slot: str = "usb",
    ) -> str | None:
        """Look up a track fingerprint by rekordbox ID and source.

        Args:
            rekordbox_id: Rekordbox track ID.
            source_player: Source player identifier (e.g. "1", "dlp", "devicesql").
            source_slot: Source slot identifier (e.g. "usb", "sd").
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT fingerprint FROM track_ids "
                "WHERE source_player = ? AND source_slot = ? AND rekordbox_id = ?",
                (source_player, source_slot, rekordbox_id),
            ).fetchone()
        return row[0] if row else None

    def link_rekordbox_id(
        self,
        rekordbox_id: int,
        fingerprint: str,
        source_player: str = "1",
        source_slot: str = "usb",
    ) -> None:
        """Associate a rekordbox ID with a track fingerprint.

        Args:
            rekordbox_id: Rekordbox track ID.
            fingerprint: Track fingerprint (SHA256).
            source_player: Source player identifier (e.g. "1", "dlp", "devicesql").
            source_slot: Source slot identifier (e.g. "usb", "sd").
        """
        import time
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO track_ids "
                "(source_player, source_slot, rekordbox_id, fingerprint, first_seen) "
                "VALUES (?, ?, ?, ?, ?)",
                (source_player, source_slot, rekordbox_id, fingerprint, time.time()),
            )

    def store_divergence(self, record: DivergenceRecord) -> None:
        """Persist a DivergenceRecord to the divergence_log table."""
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO divergence_log
                (track_fingerprint, field, scue_value, pioneer_value, resolution, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                record.track_fingerprint,
                record.divergence_field,
                record.scue_value,
                record.pioneer_value,
                record.resolution,
                record.timestamp,
            ))

    def query_divergences(
        self,
        track_fingerprint: str | None = None,
        divergence_field: str | None = None,
    ) -> list[DivergenceRecord]:
        """Query logged divergences, optionally filtered."""
        query = "SELECT track_fingerprint, field, scue_value, pioneer_value, resolution, timestamp FROM divergence_log"
        params: list = []
        conditions = []
        if track_fingerprint:
            conditions.append("track_fingerprint = ?")
            params.append(track_fingerprint)
        if divergence_field:
            conditions.append("field = ?")
            params.append(divergence_field)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            DivergenceRecord(
                track_fingerprint=r[0],
                divergence_field=r[1],
                scue_value=r[2],
                pioneer_value=r[3],
                resolution=r[4],
                timestamp=r[5],
            )
            for r in rows
        ]

    def store_pioneer_metadata(
        self,
        rekordbox_id: int,
        metadata: dict,
        source_player: str = "1",
        source_slot: str = "usb",
    ) -> None:
        """Cache Pioneer metadata from a USB scan for later enrichment.

        Args:
            rekordbox_id: Track ID from the USB database.
            metadata: Dict with keys: title, artist, bpm, key_name,
                      beatgrid (list[float]), cue_points (list[dict]),
                      memory_points (list[dict]), hot_cues (list[dict]),
                      file_path, scan_timestamp.
            source_player: Source player identifier (e.g. "1", "dlp", "devicesql").
            source_slot: Source slot identifier (e.g. "usb", "sd").
        """
        import time as _time

        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO pioneer_metadata
                (source_player, source_slot, rekordbox_id, title, artist, bpm, key_name,
                 beatgrid_json, cue_points_json, memory_points_json, hot_cues_json,
                 file_path, scan_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source_player,
                source_slot,
                rekordbox_id,
                metadata.get("title", ""),
                metadata.get("artist", ""),
                metadata.get("bpm", 0.0),
                metadata.get("key_name", ""),
                json.dumps(metadata.get("beatgrid", [])),
                json.dumps(metadata.get("cue_points", [])),
                json.dumps(metadata.get("memory_points", [])),
                json.dumps(metadata.get("hot_cues", [])),
                metadata.get("file_path", ""),
                metadata.get("scan_timestamp", _time.time()),
            ))

    def get_pioneer_metadata(
        self,
        rekordbox_id: int,
        source_player: str = "1",
        source_slot: str = "usb",
    ) -> dict | None:
        """Retrieve cached Pioneer metadata for a track.

        Args:
            rekordbox_id: Rekordbox track ID.
            source_player: Source player identifier (e.g. "1", "dlp", "devicesql").
            source_slot: Source slot identifier (e.g. "usb", "sd").

        Returns:
            Dict with beatgrid (list[float]), cue_points, memory_points,
            hot_cues, title, artist, bpm, key_name, file_path.
            None if no metadata cached for this ID.
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM pioneer_metadata "
                "WHERE source_player = ? AND source_slot = ? AND rekordbox_id = ?",
                (source_player, source_slot, rekordbox_id),
            ).fetchone()

        if row is None:
            return None

        return {
            "rekordbox_id": row["rekordbox_id"],
            "title": row["title"],
            "artist": row["artist"],
            "bpm": row["bpm"],
            "key_name": row["key_name"],
            "beatgrid": json.loads(row["beatgrid_json"]),
            "cue_points": json.loads(row["cue_points_json"]),
            "memory_points": json.loads(row["memory_points_json"]),
            "hot_cues": json.loads(row["hot_cues_json"]),
            "file_path": row["file_path"],
            "scan_timestamp": row["scan_timestamp"],
        }

    def list_pioneer_metadata(self) -> list[dict]:
        """List all cached Pioneer metadata (for UI / debugging)."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT rekordbox_id, title, artist, bpm, key_name, file_path, scan_timestamp "
                "FROM pioneer_metadata ORDER BY title"
            ).fetchall()

        return [dict(row) for row in rows]

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
