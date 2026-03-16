"""REST API endpoints for track management.

Provides CRUD operations for track analyses:
- GET /api/tracks — list all analyzed tracks (from SQLite cache)
- GET /api/tracks/{fingerprint} — get full analysis (from JSON)
- POST /api/tracks/analyze — trigger analysis of an audio file
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from ..layer1.models import analysis_to_dict
from ..layer1.storage import TrackCache, TrackStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tracks", tags=["tracks"])

# These will be initialized by the app startup
_store: TrackStore | None = None
_cache: TrackCache | None = None
_tracks_dir: Path | None = None
_cache_path: Path | None = None


def init_tracks_api(tracks_dir: Path, cache_path: Path) -> None:
    """Initialize the tracks API with storage paths.

    Called during app startup.
    """
    global _store, _cache, _tracks_dir, _cache_path
    _tracks_dir = tracks_dir
    _cache_path = cache_path
    _store = TrackStore(tracks_dir)
    _cache = TrackCache(cache_path)
    logger.info("Tracks API initialized: tracks=%s, cache=%s", tracks_dir, cache_path)


def _get_store() -> TrackStore:
    if _store is None:
        raise HTTPException(500, "Track store not initialized")
    return _store


def _get_cache() -> TrackCache:
    if _cache is None:
        raise HTTPException(500, "Track cache not initialized")
    return _cache


@router.get("")
async def list_tracks(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at"),
    sort_desc: bool = Query(True),
) -> dict:
    """List all analyzed tracks.

    Returns flattened metadata from the SQLite cache (fast).
    """
    cache = _get_cache()
    tracks = cache.list_tracks(limit=limit, offset=offset, sort_by=sort_by, sort_desc=sort_desc)
    total = cache.count_tracks()
    return {"tracks": tracks, "total": total}


@router.get("/{fingerprint}")
async def get_track(fingerprint: str) -> dict:
    """Get full analysis for a specific track.

    Reads from JSON (source of truth), not SQLite cache.
    """
    store = _get_store()
    analysis = store.load_latest(fingerprint)
    if analysis is None:
        raise HTTPException(404, f"Track not found: {fingerprint[:16]}")
    return analysis_to_dict(analysis)


@router.post("/analyze")
async def analyze_track(
    audio_path: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
    skip_waveform: bool = False,
) -> dict:
    """Trigger analysis of an audio file.

    Analysis runs in a background task. Returns immediately with
    the fingerprint so the client can poll for completion.
    """
    from ..layer1.analysis import run_analysis
    from ..layer1.fingerprint import compute_fingerprint

    path = Path(audio_path)
    if not path.exists():
        raise HTTPException(400, f"Audio file not found: {audio_path}")

    fingerprint = compute_fingerprint(path)

    # Check if already analyzed
    store = _get_store()
    if not force and store.exists(fingerprint):
        return {
            "status": "already_analyzed",
            "fingerprint": fingerprint,
        }

    # Run in background
    background_tasks.add_task(
        _run_analysis_task,
        audio_path=str(path),
        force=force,
        skip_waveform=skip_waveform,
    )

    return {
        "status": "analyzing",
        "fingerprint": fingerprint,
        "audio_path": str(path),
    }


async def _run_analysis_task(
    audio_path: str,
    force: bool = False,
    skip_waveform: bool = False,
) -> None:
    """Background task for track analysis."""
    from ..layer1.analysis import run_analysis

    try:
        run_analysis(
            audio_path=audio_path,
            tracks_dir=_tracks_dir,
            cache_path=_cache_path,
            force=force,
            skip_waveform=skip_waveform,
        )
        logger.info("Background analysis complete: %s", audio_path)
    except Exception:
        logger.exception("Background analysis failed: %s", audio_path)
