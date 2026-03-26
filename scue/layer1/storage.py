"""Track analysis storage — JSON files (source of truth) + SQLite (derived cache).

JSON files in the project's tracks/ directory are the canonical store.
SQLite in cache/ is a derived index rebuilt from JSON. If the DB is deleted,
nothing is lost — it's rebuilt on next access.

All writes go to JSON first, then update SQLite.
"""

from __future__ import annotations

import base64
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

    # ------------------------------------------------------------------
    # Live Pioneer data persistence
    # ------------------------------------------------------------------

    def _live_data_path(self, fingerprint: str) -> Path:
        """Path for the live Pioneer data sidecar file."""
        track_dir = self.tracks_dir / fingerprint
        return track_dir / "live_pioneer.json"

    def save_live_data(self, fingerprint: str, data: dict) -> Path:
        """Save live Pioneer data captured from hardware.

        Overwrites any existing data for this track (newer data wins).

        Args:
            fingerprint: Track fingerprint (SHA256).
            data: Dict containing phrases, beat_grid, cue_points, etc.

        Returns:
            Path to the saved JSON file.
        """
        path = self._live_data_path(fingerprint)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved live Pioneer data for %s", fingerprint[:12])
        return path

    def load_live_data(self, fingerprint: str) -> dict | None:
        """Load saved live Pioneer data for a track.

        Returns:
            Dict with captured Pioneer data, or None if not available.
        """
        path = self._live_data_path(fingerprint)
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load live data for %s: %s", fingerprint[:12], e)
            return None

    def has_live_data(self, fingerprint: str) -> bool:
        """Check if live Pioneer data exists for a track."""
        return self._live_data_path(fingerprint).exists()


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


def _migrate_tracks_add_folder(conn: sqlite3.Connection) -> None:
    """Add folder column to tracks table if missing.

    No data loss — new column gets empty default. Existing tracks appear at root.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='tracks'"
    ).fetchone()
    if row and "folder" not in row[0]:
        logger.info("Migrating tracks table: adding folder column")
        conn.execute(
            "ALTER TABLE tracks ADD COLUMN folder TEXT NOT NULL DEFAULT ''"
        )


def _migrate_tracks_add_has_live_data(conn: sqlite3.Connection) -> None:
    """Add has_live_data column to tracks table if missing."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='tracks'"
    ).fetchone()
    if row and "has_live_data" not in row[0]:
        logger.info("Migrating tracks table: adding has_live_data column")
        conn.execute(
            "ALTER TABLE tracks ADD COLUMN has_live_data INTEGER NOT NULL DEFAULT 0"
        )


def _migrate_pioneer_metadata_waveforms(conn: sqlite3.Connection) -> None:
    """Add waveform columns to existing pioneer_metadata table if missing.

    Data loss: none — new columns get empty defaults. USB rescan repopulates.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='pioneer_metadata'"
    ).fetchone()
    if row and "waveform_pwv5" not in row[0]:
        logger.info("Migrating pioneer_metadata: adding waveform columns")
        for col in ("waveform_pwv5", "waveform_pwv3", "waveform_pwv7"):
            conn.execute(
                f"ALTER TABLE pioneer_metadata ADD COLUMN {col} TEXT NOT NULL DEFAULT ''"
            )


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
                    folder TEXT NOT NULL DEFAULT '',
                    has_live_data INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (fingerprint, version)
                )
            """)
            # Migration: add folder column to existing tracks table
            _migrate_tracks_add_folder(conn)
            # Migration: add has_live_data column to existing tracks table
            _migrate_tracks_add_has_live_data(conn)
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
                    waveform_pwv5 TEXT NOT NULL DEFAULT '',
                    waveform_pwv3 TEXT NOT NULL DEFAULT '',
                    waveform_pwv7 TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (source_player, source_slot, rekordbox_id)
                )
            """)
            _migrate_pioneer_metadata_waveforms(conn)

            # Settings key-value store (persists across restarts)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            # Bridge scan data — tracks scanned via CDJ load (command channel)
            # Separate from pioneer_metadata (which comes from USB ANLZ scanning)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bridge_scan_data (
                    source_player TEXT NOT NULL,
                    source_slot TEXT NOT NULL,
                    rekordbox_id INTEGER NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    artist TEXT NOT NULL DEFAULT '',
                    album TEXT NOT NULL DEFAULT '',
                    genre TEXT NOT NULL DEFAULT '',
                    key_name TEXT NOT NULL DEFAULT '',
                    bpm REAL NOT NULL DEFAULT 0.0,
                    duration REAL NOT NULL DEFAULT 0.0,
                    color TEXT,
                    rating INTEGER NOT NULL DEFAULT 0,
                    comment TEXT NOT NULL DEFAULT '',
                    beatgrid_json TEXT NOT NULL DEFAULT '[]',
                    phrases_json TEXT NOT NULL DEFAULT '[]',
                    cue_points_json TEXT NOT NULL DEFAULT '[]',
                    memory_points_json TEXT NOT NULL DEFAULT '[]',
                    hot_cues_json TEXT NOT NULL DEFAULT '[]',
                    waveform_data TEXT NOT NULL DEFAULT '',
                    waveform_frame_count INTEGER NOT NULL DEFAULT 0,
                    waveform_total_time_ms INTEGER NOT NULL DEFAULT 0,
                    waveform_is_color INTEGER NOT NULL DEFAULT 1,
                    scan_timestamp REAL NOT NULL,
                    PRIMARY KEY (source_player, source_slot, rekordbox_id)
                )
            """)

            # Job persistence (survives server restarts)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'pending',
                    total INTEGER NOT NULL DEFAULT 0,
                    completed INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    current_file TEXT,
                    current_step INTEGER NOT NULL DEFAULT 0,
                    current_step_name TEXT NOT NULL DEFAULT '',
                    total_steps INTEGER NOT NULL DEFAULT 10,
                    scan_root TEXT NOT NULL DEFAULT '',
                    destination_folder TEXT NOT NULL DEFAULT '',
                    skip_waveform INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analysis_job_files (
                    job_id TEXT NOT NULL,
                    file_index INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    fingerprint TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    error TEXT,
                    PRIMARY KEY (job_id, file_index),
                    FOREIGN KEY (job_id) REFERENCES analysis_jobs(job_id)
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(str(self.db_path))

    def index_analysis(self, analysis: TrackAnalysis, has_live_data: bool = False) -> None:
        """Add or update a track analysis in the cache.

        Args:
            analysis: The TrackAnalysis to index.
            has_live_data: Whether live Pioneer data exists for this track.
        """
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tracks
                (fingerprint, version, source, audio_path, title, artist,
                 bpm, duration, section_count, mood, key_name, created_at, folder,
                 has_live_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                analysis.folder,
                int(has_live_data),
            ))

    def set_has_live_data(self, fingerprint: str, value: bool = True) -> None:
        """Set the has_live_data flag for a track in the cache."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE tracks SET has_live_data = ? WHERE fingerprint = ?",
                (int(value), fingerprint),
            )

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
        valid_sorts = {"created_at", "title", "artist", "bpm", "duration", "folder"}
        if sort_by not in valid_sorts:
            sort_by = "created_at"

        direction = "DESC" if sort_desc else "ASC"

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"""
                SELECT fingerprint, version, source, audio_path, title, artist,
                       bpm, duration, section_count, mood, key_name, created_at, folder,
                       has_live_data
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

        # Encode waveform bytes to base64 for TEXT column storage
        wf_pwv5 = metadata.get("waveform_pwv5", b"")
        wf_pwv3 = metadata.get("waveform_pwv3", b"")
        wf_pwv7 = metadata.get("waveform_pwv7", b"")
        wf_pwv5_b64 = base64.b64encode(wf_pwv5).decode("ascii") if wf_pwv5 else ""
        wf_pwv3_b64 = base64.b64encode(wf_pwv3).decode("ascii") if wf_pwv3 else ""
        wf_pwv7_b64 = base64.b64encode(wf_pwv7).decode("ascii") if wf_pwv7 else ""

        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO pioneer_metadata
                (source_player, source_slot, rekordbox_id, title, artist, bpm, key_name,
                 beatgrid_json, cue_points_json, memory_points_json, hot_cues_json,
                 file_path, scan_timestamp, waveform_pwv5, waveform_pwv3, waveform_pwv7)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                wf_pwv5_b64,
                wf_pwv3_b64,
                wf_pwv7_b64,
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

        # Decode waveform base64 back to bytes
        wf_pwv5_b64 = row["waveform_pwv5"] if "waveform_pwv5" in row.keys() else ""
        wf_pwv3_b64 = row["waveform_pwv3"] if "waveform_pwv3" in row.keys() else ""
        wf_pwv7_b64 = row["waveform_pwv7"] if "waveform_pwv7" in row.keys() else ""

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
            "waveform_pwv5": base64.b64decode(wf_pwv5_b64) if wf_pwv5_b64 else b"",
            "waveform_pwv3": base64.b64decode(wf_pwv3_b64) if wf_pwv3_b64 else b"",
            "waveform_pwv7": base64.b64decode(wf_pwv7_b64) if wf_pwv7_b64 else b"",
        }

    def get_pioneer_waveforms_by_fingerprint(
        self,
        fingerprint: str,
    ) -> dict | None:
        """Look up Pioneer waveform data for a track by its SCUE fingerprint.

        Performs a reverse lookup: fingerprint → track_ids → pioneer_metadata.
        Returns the first pioneer_metadata row that has waveform data.

        Returns:
            Dict with waveform_pwv5, waveform_pwv3, waveform_pwv7 (bytes).
            None if no waveform data found.
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            # Find all (source_player, source_slot, rekordbox_id) for this fingerprint
            id_rows = conn.execute(
                "SELECT source_player, source_slot, rekordbox_id "
                "FROM track_ids WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchall()

        if not id_rows:
            return None

        # Check each for waveform data
        for id_row in id_rows:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                meta_row = conn.execute(
                    "SELECT waveform_pwv5, waveform_pwv3, waveform_pwv7 "
                    "FROM pioneer_metadata "
                    "WHERE source_player = ? AND source_slot = ? AND rekordbox_id = ?",
                    (id_row["source_player"], id_row["source_slot"], id_row["rekordbox_id"]),
                ).fetchone()

            if meta_row is None:
                continue

            pwv5_b64 = meta_row["waveform_pwv5"] or ""
            pwv3_b64 = meta_row["waveform_pwv3"] or ""
            pwv7_b64 = meta_row["waveform_pwv7"] or ""

            if pwv5_b64 or pwv3_b64 or pwv7_b64:
                return {
                    "waveform_pwv5": base64.b64decode(pwv5_b64) if pwv5_b64 else b"",
                    "waveform_pwv3": base64.b64decode(pwv3_b64) if pwv3_b64 else b"",
                    "waveform_pwv7": base64.b64decode(pwv7_b64) if pwv7_b64 else b"",
                }

        return None

    def list_pioneer_metadata(self) -> list[dict]:
        """List all cached Pioneer metadata (for UI / debugging)."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT rekordbox_id, title, artist, bpm, key_name, file_path, scan_timestamp "
                "FROM pioneer_metadata ORDER BY title"
            ).fetchall()

        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Folder-aware queries
    # ------------------------------------------------------------------

    def list_tracks_in_folder(
        self,
        folder: str = "",
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ) -> list[dict]:
        """List tracks at an exact folder level (not recursive)."""
        valid_sorts = {"created_at", "title", "artist", "bpm", "duration", "folder"}
        if sort_by not in valid_sorts:
            sort_by = "created_at"
        direction = "DESC" if sort_desc else "ASC"

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"""
                SELECT fingerprint, version, source, audio_path, title, artist,
                       bpm, duration, section_count, mood, key_name, created_at, folder,
                       has_live_data
                FROM tracks
                WHERE folder = ?
                  AND version = (
                      SELECT MAX(version) FROM tracks t2
                      WHERE t2.fingerprint = tracks.fingerprint
                  )
                ORDER BY {sort_by} {direction}
                LIMIT ? OFFSET ?
            """, (folder, limit, offset)).fetchall()

        return [dict(row) for row in rows]

    def list_subfolders(self, parent_folder: str = "") -> list[dict]:
        """List immediate child folders under a parent folder.

        Returns list of dicts with 'name', 'path', and 'track_count' keys.
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            # Get all distinct folders for latest versions
            rows = conn.execute("""
                SELECT folder, COUNT(DISTINCT fingerprint) as cnt
                FROM tracks
                WHERE version = (
                    SELECT MAX(version) FROM tracks t2
                    WHERE t2.fingerprint = tracks.fingerprint
                )
                AND folder != ''
                GROUP BY folder
            """).fetchall()

        # Extract immediate children of parent_folder
        prefix = (parent_folder + "/") if parent_folder else ""
        child_counts: dict[str, int] = {}

        for row in rows:
            folder_path = row["folder"]
            if parent_folder == "":
                # Root level: get first segment
                segment = folder_path.split("/")[0]
                child_path = segment
            elif folder_path.startswith(prefix):
                # Under parent: get next segment
                remainder = folder_path[len(prefix):]
                if not remainder:
                    continue  # exact match, not a child
                segment = remainder.split("/")[0]
                child_path = prefix + segment
            else:
                continue

            child_counts[child_path] = child_counts.get(child_path, 0) + row["cnt"]

        return [
            {"name": path.rsplit("/", 1)[-1] if "/" in path else path,
             "path": path,
             "track_count": count}
            for path, count in sorted(child_counts.items())
        ]

    def count_tracks_in_folder(self, folder: str = "") -> int:
        """Count tracks at an exact folder level."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT fingerprint) FROM tracks WHERE folder = ?",
                (folder,),
            ).fetchone()
        return row[0] if row else 0

    def list_tracks_under_folder(
        self,
        folder: str = "",
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ) -> list[dict]:
        """List all tracks under a folder recursively (includes subfolders)."""
        valid_sorts = {"created_at", "title", "artist", "bpm", "duration", "folder"}
        if sort_by not in valid_sorts:
            sort_by = "created_at"
        direction = "DESC" if sort_desc else "ASC"

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if folder:
                rows = conn.execute(f"""
                    SELECT fingerprint, version, source, audio_path, title, artist,
                           bpm, duration, section_count, mood, key_name, created_at, folder
                    FROM tracks
                    WHERE (folder = ? OR folder LIKE ? || '/%')
                      AND version = (
                          SELECT MAX(version) FROM tracks t2
                          WHERE t2.fingerprint = tracks.fingerprint
                      )
                    ORDER BY {sort_by} {direction}
                    LIMIT ? OFFSET ?
                """, (folder, folder, limit, offset)).fetchall()
            else:
                # Root: return all tracks
                rows = conn.execute(f"""
                    SELECT fingerprint, version, source, audio_path, title, artist,
                           bpm, duration, section_count, mood, key_name, created_at, folder
                    FROM tracks
                    WHERE version = (
                        SELECT MAX(version) FROM tracks t2
                        WHERE t2.fingerprint = tracks.fingerprint
                    )
                    ORDER BY {sort_by} {direction}
                    LIMIT ? OFFSET ?
                """, (limit, offset)).fetchall()

        return [dict(row) for row in rows]

    def update_track_folder(self, fingerprint: str, folder: str) -> None:
        """Move a track to a different folder. Updates all versions in the cache."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE tracks SET folder = ? WHERE fingerprint = ?",
                (folder, fingerprint),
            )

    # ------------------------------------------------------------------
    # Settings (key-value store)
    # ------------------------------------------------------------------

    def get_setting(self, key: str) -> str | None:
        """Get a setting value by key."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        """Set a setting value."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

    # ------------------------------------------------------------------
    # Job persistence
    # ------------------------------------------------------------------

    def create_job(
        self,
        job_id: str,
        paths: list[str],
        scan_root: str = "",
        destination_folder: str = "",
        skip_waveform: bool = False,
    ) -> None:
        """Persist a new analysis job to SQLite."""
        import time as _time
        now = _time.time()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO analysis_jobs
                (job_id, status, total, completed, failed, current_file,
                 current_step, current_step_name, total_steps,
                 scan_root, destination_folder, skip_waveform, created_at, updated_at)
                VALUES (?, 'pending', ?, 0, 0, NULL, 0, '', 10, ?, ?, ?, ?, ?)
            """, (job_id, len(paths), scan_root, destination_folder,
                  int(skip_waveform), now, now))

            for i, p in enumerate(paths):
                filename = p.rsplit("/", 1)[-1] if "/" in p else p
                conn.execute("""
                    INSERT INTO analysis_job_files
                    (job_id, file_index, path, filename, fingerprint, status, error)
                    VALUES (?, ?, ?, ?, '', 'pending', NULL)
                """, (job_id, i, p, filename))

    def update_job_progress(self, job_id: str, **fields: object) -> None:
        """Update job-level fields (status, completed, failed, current_file, etc.)."""
        import time as _time
        allowed = {"status", "total", "completed", "failed", "current_file",
                    "current_step", "current_step_name", "total_steps"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        updates["updated_at"] = _time.time()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [job_id]
        with self._connect() as conn:
            conn.execute(
                f"UPDATE analysis_jobs SET {set_clause} WHERE job_id = ?",
                values,
            )

    def update_job_file(
        self,
        job_id: str,
        file_index: int,
        status: str,
        fingerprint: str = "",
        error: str | None = None,
    ) -> None:
        """Update a single file result within a job."""
        with self._connect() as conn:
            conn.execute("""
                UPDATE analysis_job_files
                SET status = ?, fingerprint = ?, error = ?
                WHERE job_id = ? AND file_index = ?
            """, (status, fingerprint, error, job_id, file_index))

    def get_job(self, job_id: str) -> dict | None:
        """Get a persisted job with its file results."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            job_row = conn.execute(
                "SELECT * FROM analysis_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not job_row:
                return None

            file_rows = conn.execute(
                "SELECT * FROM analysis_job_files WHERE job_id = ? ORDER BY file_index",
                (job_id,),
            ).fetchall()

        return {
            **dict(job_row),
            "results": [dict(r) for r in file_rows],
        }

    def get_incomplete_jobs(self) -> list[dict]:
        """Get all jobs that haven't finished (for resume on startup)."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM analysis_jobs WHERE status IN ('pending', 'running')"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_job_pending_files(self, job_id: str) -> list[dict]:
        """Get pending (un-processed) files for a job."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM analysis_job_files WHERE job_id = ? AND status = 'pending' "
                "ORDER BY file_index",
                (job_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Bridge scan data (CDJ-loaded track capture)
    # ------------------------------------------------------------------

    def has_pioneer_scan_data(
        self,
        source_player: int,
        source_slot: str,
        rekordbox_id: int,
    ) -> bool:
        """Check if a track has already been scanned via bridge command channel."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM bridge_scan_data "
                "WHERE source_player = ? AND source_slot = ? AND rekordbox_id = ?",
                (str(source_player), source_slot, rekordbox_id),
            ).fetchone()
        return row is not None

    def store_bridge_scan_data(
        self,
        source_player: int,
        source_slot: str,
        data: dict,
    ) -> None:
        """Store captured Pioneer data from a bridge scan."""
        import time as _time
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO bridge_scan_data
                (source_player, source_slot, rekordbox_id, title, artist, album, genre,
                 key_name, bpm, duration, color, rating, comment,
                 beatgrid_json, phrases_json, cue_points_json, memory_points_json, hot_cues_json,
                 waveform_data, waveform_frame_count, waveform_total_time_ms, waveform_is_color,
                 scan_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(source_player),
                source_slot,
                data.get("rekordbox_id", 0),
                data.get("title", ""),
                data.get("artist", ""),
                data.get("album", ""),
                data.get("genre", ""),
                data.get("key", ""),
                data.get("bpm", 0.0),
                data.get("duration", 0.0),
                data.get("color"),
                data.get("rating", 0),
                data.get("comment", ""),
                json.dumps(data.get("beat_grid", [])),
                json.dumps(data.get("phrases", [])),
                json.dumps(data.get("cue_points", [])),
                json.dumps(data.get("memory_points", [])),
                json.dumps(data.get("hot_cues", [])),
                data.get("waveform_data", ""),
                data.get("waveform_frame_count", 0),
                data.get("waveform_total_time_ms", 0),
                int(data.get("waveform_is_color", True)),
                _time.time(),
            ))

    def get_bridge_scan_data(
        self,
        source_player: int,
        source_slot: str,
        rekordbox_id: int,
    ) -> dict | None:
        """Get stored bridge scan data for a track."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM bridge_scan_data "
                "WHERE source_player = ? AND source_slot = ? AND rekordbox_id = ?",
                (str(source_player), source_slot, rekordbox_id),
            ).fetchone()
        return dict(row) if row else None

    def list_bridge_scan_data(self) -> list[dict]:
        """List all bridge-scanned tracks."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT rekordbox_id, title, artist, bpm, key_name, scan_timestamp "
                "FROM bridge_scan_data ORDER BY title"
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
            analysis = store.load_latest(fingerprint)
            if analysis:
                self.index_analysis(analysis)
                count += 1

        logger.info("Cache rebuilt: %d tracks indexed", count)
        return count
