"""SQLite storage for TrackAnalysis objects — Layer 1A.

Keyed by SHA256 track fingerprint. Supports versioned analyses
(pre- and post-Pioneer enrichment stored separately).
"""

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .models import TrackAnalysis, Section, MusicalEvent, TrackFeatures

log = logging.getLogger(__name__)

# Default database location
DB_PATH = Path(__file__).parent.parent.parent / "data" / "scue.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    fingerprint TEXT NOT NULL,
    version     INTEGER NOT NULL,
    source      TEXT NOT NULL DEFAULT 'analysis',
    audio_path  TEXT NOT NULL DEFAULT '',
    data_json   TEXT NOT NULL,
    created_at  REAL NOT NULL,
    PRIMARY KEY (fingerprint, version)
);

CREATE TABLE IF NOT EXISTS track_ids (
    rekordbox_id INTEGER PRIMARY KEY,
    fingerprint  TEXT NOT NULL,
    first_seen   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS divergence_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    track_fingerprint TEXT NOT NULL,
    field             TEXT NOT NULL,
    scue_value        TEXT NOT NULL,
    pioneer_value     TEXT NOT NULL,
    resolution        TEXT NOT NULL,
    timestamp         REAL NOT NULL
);
"""


def _get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open (and initialise schema on first use) a SQLite connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def fingerprint(audio_path: str) -> str:
    """Compute SHA256 fingerprint of an audio file."""
    h = hashlib.sha256()
    with open(audio_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Serialization helpers ────────────────────────────────────────────────

def _analysis_to_json(analysis: TrackAnalysis) -> str:
    """Serialize a TrackAnalysis to a JSON string."""
    d = asdict(analysis)
    return json.dumps(d)


def _analysis_from_json(raw: str) -> TrackAnalysis:
    """Deserialize a TrackAnalysis from a JSON string."""
    d = json.loads(raw)
    sections = [Section(**s) for s in d.pop("sections", [])]
    events = [MusicalEvent(**e) for e in d.pop("events", [])]
    features = TrackFeatures(**d.pop("features", {}))
    return TrackAnalysis(
        **d,
        sections=sections,
        events=events,
        features=features,
    )


# ── CRUD ─────────────────────────────────────────────────────────────────

def store_analysis(analysis: TrackAnalysis, db_path: Path = DB_PATH) -> None:
    """Persist a TrackAnalysis. Upserts by (fingerprint, version)."""
    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO tracks
               (fingerprint, version, source, audio_path, data_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                analysis.fingerprint,
                analysis.version,
                analysis.beatgrid_source,
                analysis.audio_path,
                _analysis_to_json(analysis),
                analysis.created_at,
            ),
        )
        conn.commit()
        log.info("Stored analysis: fp=%s v=%d", analysis.fingerprint[:12], analysis.version)
    finally:
        conn.close()


def load_analysis(
    fp: str,
    version: Optional[int] = None,
    db_path: Path = DB_PATH,
) -> Optional[TrackAnalysis]:
    """Load a TrackAnalysis by fingerprint. Returns latest version if version is None."""
    conn = _get_conn(db_path)
    try:
        if version is not None:
            row = conn.execute(
                "SELECT data_json FROM tracks WHERE fingerprint = ? AND version = ?",
                (fp, version),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT data_json FROM tracks WHERE fingerprint = ? ORDER BY version DESC LIMIT 1",
                (fp,),
            ).fetchone()
        if row is None:
            return None
        return _analysis_from_json(row["data_json"])
    finally:
        conn.close()


def list_tracks(db_path: Path = DB_PATH) -> list[dict]:
    """Return summary info for all stored tracks (latest version each)."""
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            """SELECT fingerprint, MAX(version) AS version, source, audio_path, created_at
               FROM tracks GROUP BY fingerprint ORDER BY created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Rekordbox ID mapping ────────────────────────────────────────────────

def map_rekordbox_id(rekordbox_id: int, fp: str, db_path: Path = DB_PATH) -> None:
    """Associate a rekordbox track ID with a fingerprint."""
    conn = _get_conn(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO track_ids (rekordbox_id, fingerprint, first_seen) VALUES (?, ?, ?)",
            (rekordbox_id, fp, time.time()),
        )
        conn.commit()
        log.info("Mapped rekordbox_id=%d → fp=%s", rekordbox_id, fp[:12])
    finally:
        conn.close()


def lookup_fingerprint(rekordbox_id: int, db_path: Path = DB_PATH) -> Optional[str]:
    """Look up a fingerprint by rekordbox track ID."""
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT fingerprint FROM track_ids WHERE rekordbox_id = ?",
            (rekordbox_id,),
        ).fetchone()
        return row["fingerprint"] if row else None
    finally:
        conn.close()


# ── Divergence log persistence ──────────────────────────────────────────

def store_divergence(
    track_fingerprint: str,
    field: str,
    scue_value: str,
    pioneer_value: str,
    resolution: str,
    timestamp: float,
    db_path: Path = DB_PATH,
) -> None:
    """Insert a divergence record into the database."""
    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT INTO divergence_log
               (track_fingerprint, field, scue_value, pioneer_value, resolution, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (track_fingerprint, field, scue_value, pioneer_value, resolution, timestamp),
        )
        conn.commit()
    finally:
        conn.close()


def query_divergences_db(
    track_fingerprint: str | None = None,
    field: str | None = None,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """Query divergence records from the database."""
    conn = _get_conn(db_path)
    try:
        query = "SELECT * FROM divergence_log WHERE 1=1"
        params: list = []
        if track_fingerprint:
            query += " AND track_fingerprint = ?"
            params.append(track_fingerprint)
        if field:
            query += " AND field = ?"
            params.append(field)
        query += " ORDER BY timestamp DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
