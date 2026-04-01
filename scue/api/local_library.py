"""Local rekordbox library API — scan and match local ANLZ files.

Endpoints for detecting, scanning, and querying the local rekordbox
library without requiring Pioneer hardware.
"""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from ..layer1.storage import TrackCache, TrackStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/local-library", tags=["local-library"])

# Set by main.py at startup
_store: TrackStore | None = None
_cache: TrackCache | None = None
_last_scan: dict | None = None
_ws_manager = None  # WSManager, set by init


def init_local_library_api(store: TrackStore, cache: TrackCache, ws_manager=None) -> None:
    """Store references for the local library endpoints."""
    global _store, _cache, _ws_manager
    _store = store
    _cache = cache
    _ws_manager = ws_manager


async def _broadcast_progress(phase: str, message: str, detail: dict | None = None) -> None:
    """Send a rekordbox_progress WS event to all connected clients."""
    if _ws_manager is None:
        return
    payload = {"phase": phase, "message": message}
    if detail:
        payload["detail"] = detail
    try:
        await _ws_manager.broadcast({"type": "rekordbox_progress", "payload": payload})
    except Exception:
        pass  # best-effort


class LocalScanRequest(BaseModel):
    """Request body for POST /api/local-library/scan."""
    path: str | None = None
    force_rescan: bool = False


@router.get("/detect")
async def detect_local_library() -> dict:
    """Detect local rekordbox ANLZ library.

    Returns library path and .DAT file count, or 404 if not found.
    """
    from ..layer1.rekordbox_scanner import detect_library

    result = detect_library()
    if result is None:
        raise HTTPException(status_code=404, detail="No local rekordbox library found")
    return result


@router.post("/scan")
async def scan_local_library(req: LocalScanRequest) -> dict:
    """Scan local rekordbox library and match tracks to SCUE analyses.

    If path is None, auto-detects the library location.
    """
    global _last_scan

    if _store is None or _cache is None:
        raise HTTPException(status_code=500, detail="Local library API not initialized")

    from ..layer1.rekordbox_scanner import (
        detect_library,
        match_local_tracks,
        scan_local_library as do_scan,
    )

    # Resolve ANLZ directory
    if req.path is not None:
        anlz_dir = Path(req.path)
        if not anlz_dir.exists():
            raise HTTPException(status_code=404, detail=f"Path not found: {req.path}")
    else:
        detected = detect_library()
        if detected is None:
            raise HTTPException(status_code=404, detail="No local rekordbox library found")
        anlz_dir = Path(detected["path"])

    # Scan and match
    local_tracks = do_scan(anlz_dir)
    result = match_local_tracks(local_tracks, _cache, _store)

    # Build response (status field enables discriminated union with /status no-scan sentinel)
    _last_scan = {
        "status": "complete",
        "source": str(anlz_dir),
        "total_tracks": result.total_tracks,
        "matched": len(result.matched),
        "unmatched": len(result.unmatched),
        "already_linked": result.already_linked,
        "scan_timestamp": result.scan_timestamp,
        "matched_tracks": [
            {
                "title": m.usb_track.title,
                "file_path": m.usb_track.file_path,
                "fingerprint": m.fingerprint[:12],
                "match_method": m.match_method,
            }
            for m in result.matched
        ],
        "unmatched_tracks": [
            {
                "title": t.title,
                "file_path": t.file_path,
            }
            for t in result.unmatched[:50]
        ],
    }

    return _last_scan


@router.get("/status")
async def local_library_status() -> dict:
    """Return the result of the last local library scan."""
    if _last_scan is None:
        return {"status": "no_scan", "message": "No local library scan has been performed yet."}
    return _last_scan


# ---------------------------------------------------------------------------
# master.db endpoints — full rekordbox desktop database access
# ---------------------------------------------------------------------------

_last_masterdb_scan: dict | None = None


@router.get("/master-db/detect")
async def detect_master_db() -> dict:
    """Check if rekordbox master.db exists."""
    from ..layer1.masterdb_scanner import detect_master_db as _detect

    path = _detect()
    if path is None:
        raise HTTPException(status_code=404, detail="rekordbox master.db not found")
    return {"path": str(path), "size_mb": round(path.stat().st_size / 1e6, 1)}


@router.post("/master-db/scan")
async def scan_master_db_endpoint() -> dict:
    """Scan rekordbox master.db and match tracks to SCUE.

    Returns collection stats and matched track list.
    Also creates Pioneer sidecars for matched tracks with ANLZ data.

    Runs CPU-bound work in a thread executor so the async event loop
    stays responsive to other requests and WebSocket traffic.
    """
    global _last_masterdb_scan

    if _store is None:
        raise HTTPException(status_code=500, detail="Store not initialized")

    from ..layer1.masterdb_scanner import create_sidecars_from_master_db, scan_master_db

    loop = asyncio.get_event_loop()

    # Progress callback bridges sync thread → async WS broadcast
    def progress_cb(current: int, total: int, message: str) -> None:
        asyncio.run_coroutine_threadsafe(
            _broadcast_progress("scanning", message, {"current": current, "total": total}),
            loop,
        )

    await _broadcast_progress("scanning", "Opening rekordbox database…")

    result = await loop.run_in_executor(
        None, lambda: scan_master_db(match_scue=True, store=_store, progress_cb=progress_cb)
    )

    await _broadcast_progress("scanning", "Creating Pioneer sidecars…")

    sidecars = await loop.run_in_executor(
        None, lambda: create_sidecars_from_master_db(result, _store)
    )

    matched = [t for t in result.tracks if t.fingerprint]
    unmatched_with_audio = [t for t in result.tracks if t.audio_exists and not t.fingerprint]

    _last_masterdb_scan = {
        "status": "complete",
        "total_tracks": result.total_tracks,
        "with_audio": result.with_audio,
        "with_anlz": result.with_anlz,
        "matched_to_scue": result.matched_to_scue,
        "sidecars_created": sidecars,
        "scan_time_seconds": result.scan_time_seconds,
        "matched_tracks": [
            {
                "fingerprint": t.fingerprint[:12],
                "title": t.title,
                "artist": t.artist,
                "bpm": t.bpm,
                "phrases": len(t.phrases),
                "beats": len(t.beatgrid),
            }
            for t in matched
        ],
        "importable_tracks": [
            {
                "title": t.title,
                "artist": t.artist,
                "bpm": t.bpm,
                "audio_path": t.audio_path,
                "phrases": len(t.phrases),
            }
            for t in unmatched_with_audio[:100]
        ],
    }

    await _broadcast_progress("complete", "Scan complete", {
        "total_tracks": result.total_tracks,
        "with_audio": result.with_audio,
        "sidecars_created": sidecars,
        "scan_time_seconds": result.scan_time_seconds,
    })

    return _last_masterdb_scan


@router.get("/master-db/status")
async def master_db_status() -> dict:
    """Return the result of the last master.db scan."""
    if _last_masterdb_scan is None:
        return {"status": "no_scan"}
    return _last_masterdb_scan


@router.get("/master-db/playlists")
async def get_master_db_playlists() -> dict:
    """Return the rekordbox playlist/folder hierarchy.

    Each node: {id, name, is_folder, track_count, children, track_ids}.
    track_ids are rekordbox content IDs that can be cross-referenced with
    scan results.
    """
    from ..layer1.masterdb_scanner import (
        scan_playlists,
        _playlist_tree_to_dict,
    )

    loop = asyncio.get_event_loop()

    try:
        tree = await loop.run_in_executor(None, scan_playlists)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="rekordbox master.db not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read playlists: {e}")

    return {"playlists": _playlist_tree_to_dict(tree)}


class MasterDbIngestRequest(BaseModel):
    """Request body for POST /api/local-library/master-db/ingest."""
    bpm_min: float | None = None
    bpm_max: float | None = None
    genre: str | None = None
    search: str | None = None
    skip_waveform: bool = False


@router.post("/master-db/ingest")
async def ingest_from_master_db_endpoint(
    req: MasterDbIngestRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Ingest tracks from rekordbox into SCUE.

    1. Reads master.db → finds tracks with audio on disk
    2. Creates Pioneer sidecars for all tracks with ANLZ data
    3. Queues new tracks for audio analysis (returns job_id for progress)

    Sidecars are created during the scan phase (run in executor) so Pioneer
    data is immediately available. Audio analysis runs in the background.
    """
    if _store is None:
        raise HTTPException(status_code=500, detail="Store not initialized")

    from ..layer1.masterdb_scanner import ingest_from_master_db

    loop = asyncio.get_event_loop()

    def progress_cb(current: int, total: int, message: str) -> None:
        asyncio.run_coroutine_threadsafe(
            _broadcast_progress("ingesting", message, {"current": current, "total": total}),
            loop,
        )

    await _broadcast_progress("ingesting", "Preparing ingest from rekordbox…")

    # Phase 1: Scan + create sidecars (in executor, ~20s)
    result = await loop.run_in_executor(
        None,
        lambda: ingest_from_master_db(
            store=_store,
            bpm_min=req.bpm_min,
            bpm_max=req.bpm_max,
            genre=req.genre,
            search=req.search,
            progress_cb=progress_cb,
        ),
    )

    response = {
        "total_in_rekordbox": result.total_in_rekordbox,
        "already_in_scue": result.already_in_scue,
        "queued_for_analysis": len(result.queued_for_analysis),
        "sidecars_created": result.sidecars_created,
        "sidecars_skipped": result.sidecars_skipped,
    }

    # Phase 2: Start batch analysis for new tracks (background)
    if result.queued_for_analysis:
        from .jobs import create_job
        from .tracks import _run_batch_analysis, _get_cache

        job = create_job(result.queued_for_analysis)
        cache = _get_cache()
        cache.create_job(
            job_id=job.job_id,
            paths=result.queued_for_analysis,
            scan_root="",
            destination_folder="rekordbox",
            skip_waveform=req.skip_waveform,
        )
        background_tasks.add_task(
            _run_batch_analysis,
            job=job,
            skip_waveform=req.skip_waveform,
            scan_root="",
            destination_folder="rekordbox",
        )
        response["job_id"] = job.job_id

    await _broadcast_progress("complete", "Ingest complete", {
        "queued": len(result.queued_for_analysis),
        "sidecars": result.sidecars_created,
    })

    return response
