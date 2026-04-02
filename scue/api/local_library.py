"""Local rekordbox library API — scan and match local ANLZ files.

Endpoints for detecting, scanning, and querying the local rekordbox
library without requiring Pioneer hardware.
"""

import asyncio
import logging
import threading
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

# Singleton ingest guard — prevents concurrent ingest processes
_ingest_lock = asyncio.Lock()
_ingest_cancel = threading.Event()  # thread-safe flag checked by executor thread


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
_last_scan_result: object | None = None  # MasterDbScanResult, kept for ingest reuse


@router.get("/master-db/detect")
async def detect_master_db() -> dict:
    """Check if rekordbox master.db exists."""
    from ..layer1.masterdb_scanner import detect_master_db as _detect

    path = _detect()
    if path is None:
        raise HTTPException(status_code=404, detail="rekordbox master.db not found")
    return {"path": str(path), "size_mb": round(path.stat().st_size / 1e6, 1)}


_scan_in_progress = False


@router.post("/master-db/scan")
async def scan_master_db_endpoint(background_tasks: BackgroundTasks) -> dict:
    """Start a rekordbox master.db scan in the background.

    Returns immediately with ``{status: "started"}``. Progress is
    broadcast via WS ``rekordbox_progress`` events. When the scan
    finishes, a ``rekordbox_progress`` event with ``phase: "scan_complete"``
    carries the full result, which is also stored in ``_last_masterdb_scan``
    (available via ``GET /master-db/status``).

    This avoids the Vite-proxy / browser timeout that killed the
    previous synchronous 130-second POST.
    """
    global _scan_in_progress

    if _store is None:
        raise HTTPException(status_code=500, detail="Store not initialized")

    if _scan_in_progress:
        return {"status": "already_scanning"}

    background_tasks.add_task(_run_scan_background)
    return {"status": "started"}


async def _run_scan_background() -> None:
    """Background task: scan master.db, create sidecars, broadcast result."""
    global _last_masterdb_scan, _last_scan_result, _scan_in_progress
    _scan_in_progress = True

    try:
        from ..layer1.masterdb_scanner import (
            create_sidecars_from_master_db,
            detect_master_db as _detect,
            scan_master_db,
        )

        loop = asyncio.get_event_loop()

        # --- Level 1: mtime gate — skip entirely if master.db unchanged ---
        db_path = _detect()
        if db_path is None:
            await _broadcast_progress("error", "rekordbox master.db not found")
            return

        prev = _last_scan_result
        if prev is not None and hasattr(prev, "db_mtime") and prev.db_mtime:
            db_stat = db_path.stat()
            if db_stat.st_mtime == prev.db_mtime and db_stat.st_size == prev.db_size:
                logger.info("master.db unchanged (mtime=%.0f, size=%d) — returning cached result", db_stat.st_mtime, db_stat.st_size)
                await _broadcast_progress("scan_complete", "No changes — using cached result", _last_masterdb_scan)
                return

        # Track which overall phase we're in so the frontend can show
        # "Step 2/4: Parsing ANLZ data" etc.
        scan_phases = [
            "Reading master.db",
            "Parsing ANLZ data",
            "Computing fingerprints",
            "Creating Pioneer sidecars",
        ]
        current_phase = {"name": scan_phases[0], "step": 1}

        def progress_cb(current: int, total: int, message: str) -> None:
            # Detect phase transitions from the message text
            for i, phase_name in enumerate(scan_phases):
                if message == phase_name:
                    current_phase["name"] = phase_name
                    current_phase["step"] = i + 1
                    break
            asyncio.run_coroutine_threadsafe(
                _broadcast_progress("scanning", message, {
                    "current": current,
                    "total": total,
                    "step": current_phase["step"],
                    "total_steps": len(scan_phases),
                    "step_name": current_phase["name"],
                }),
                loop,
            )

        await _broadcast_progress("scanning", "Opening rekordbox database…", {
            "step": 1, "total_steps": len(scan_phases), "step_name": scan_phases[0],
        })

        # --- Level 2: incremental diff — pass previous result for carry-forward ---
        result = await loop.run_in_executor(
            None, lambda: scan_master_db(
                db_path=db_path,
                match_scue=True,
                store=_store,
                progress_cb=progress_cb,
                previous_result=prev,
            )
        )

        # Keep full result for ingest reuse (avoids re-scanning on import)
        _last_scan_result = result

        await _broadcast_progress("scanning", "Creating Pioneer sidecars…", {
            "step": 4, "total_steps": len(scan_phases), "step_name": scan_phases[3],
        })

        sidecars = await loop.run_in_executor(
            None, lambda: create_sidecars_from_master_db(result, _store)
        )

        matched = [t for t in result.tracks if t.fingerprint and _store.exists(t.fingerprint)]
        unmatched_with_audio = [t for t in result.tracks if t.audio_exists and (not t.fingerprint or not _store.exists(t.fingerprint))]

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

        await _broadcast_progress("scan_complete", "Scan complete", _last_masterdb_scan)
        logger.info(
            "Scan complete: %d tracks, %d matched, %d sidecars in %.1fs",
            result.total_tracks, result.matched_to_scue, sidecars, result.scan_time_seconds,
        )

    except Exception as e:
        logger.exception("Background scan failed: %s", e)
        await _broadcast_progress("error", f"Scan failed: {e}")
    finally:
        _scan_in_progress = False


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
    metadata_only: bool = False  # If True, only create sidecars — skip audio analysis


_ingest_in_progress = False


@router.post("/master-db/ingest")
async def ingest_from_master_db_endpoint(
    req: MasterDbIngestRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Start ingestion from rekordbox master.db in the background.

    Returns immediately with ``{status: "started"}``. Progress is
    broadcast via WS ``rekordbox_progress`` events. When the ingest
    finishes, a ``rekordbox_progress`` event with ``phase: "ingest_complete"``
    carries the result summary.

    Singleton: only one ingest runs at a time.
    """
    global _ingest_in_progress

    if _store is None:
        raise HTTPException(status_code=500, detail="Store not initialized")

    # Cancel any in-progress ingest before starting a new one
    if _ingest_in_progress:
        logger.info("Cancelling previous ingest to start a new one")
        _ingest_cancel.set()
        return {"status": "cancelling_previous", "message": "Previous ingest being cancelled, try again shortly"}

    _ingest_in_progress = True  # Set immediately in endpoint, not background task

    background_tasks.add_task(
        _run_ingest_background,
        bpm_min=req.bpm_min,
        bpm_max=req.bpm_max,
        genre=req.genre,
        search=req.search,
        skip_waveform=req.skip_waveform,
        metadata_only=req.metadata_only,
    )
    return {"status": "started"}


async def _run_ingest_background(
    *,
    bpm_min: float | None,
    bpm_max: float | None,
    genre: str | None,
    search: str | None,
    skip_waveform: bool,
    metadata_only: bool,
) -> None:
    """Background task: run ingest, broadcast progress + result via WS.

    If a scan was already performed (``_last_scan_result`` is set), reuses
    its fingerprints and ANLZ data instead of re-reading master.db from
    scratch.  Only falls back to a full ``ingest_from_master_db()`` when no
    prior scan exists.
    """
    global _ingest_in_progress

    async with _ingest_lock:
        _ingest_cancel.clear()

        try:
            loop = asyncio.get_event_loop()

            # ----- Fast path: reuse scan result ---------------------------
            if _last_scan_result is not None:
                from ..layer1.masterdb_scanner import MasterDbScanResult, MasterDbTrack, _compute_fingerprint
                from pathlib import Path

                scan: MasterDbScanResult = _last_scan_result  # type: ignore[assignment]

                await _broadcast_progress("ingesting", "Creating sidecars from scan results…", {
                    "step": 1, "total_steps": 1, "step_name": "Creating sidecars",
                })

                # Tracks already fingerprinted during scan — just classify
                already_in_scue = 0
                queued: list[str] = []
                sidecars_created = 0
                sidecars_skipped = 0

                for i, track in enumerate(scan.tracks):
                    if _ingest_cancel.is_set():
                        logger.info("Ingest cancelled during sidecar creation")
                        await _broadcast_progress("cancelled", "Ingest cancelled")
                        return

                    if not track.audio_exists:
                        continue

                    fp = track.fingerprint
                    if fp is None:
                        # Track wasn't fingerprinted during scan (no audio match)
                        queued.append(track.audio_path)
                        sidecars_skipped += 1
                        continue

                    if _store.exists(fp):
                        already_in_scue += 1
                    else:
                        queued.append(track.audio_path)

                    # Create sidecar if ANLZ data available
                    if track.phrases or track.beatgrid:
                        duration = 0.0
                        if _store.exists(fp):
                            analysis = _store.load_latest(fp)
                            if analysis:
                                duration = analysis.duration
                        if duration <= 0 and track.duration_ms:
                            duration = track.duration_ms / 1000.0

                        sidecar = {
                            "fingerprint": fp,
                            "rekordbox_id": track.rekordbox_id,
                            "title": track.title,
                            "artist": track.artist,
                            "bpm": track.bpm,
                            "duration": duration,
                            "phrases": track.phrases,
                            "beat_grid": track.beatgrid,
                            "hot_cues": track.hot_cues,
                            "memory_points": track.memory_points,
                            "source": "master_db",
                        }
                        _store.save_live_data(fp, sidecar)
                        sidecars_created += 1
                    else:
                        sidecars_skipped += 1

                    # Index in cache so track appears in SCUE Library
                    # (version=0, INSERT OR IGNORE — won't overwrite real analysis)
                    if _cache is not None:
                        _cache.index_sidecar(
                            fingerprint=fp,
                            audio_path=track.audio_path,
                            title=track.title,
                            artist=track.artist,
                            bpm=track.bpm,
                            duration=(track.duration_ms / 1000.0) if track.duration_ms else 0.0,
                        )

                    if i % 100 == 0:
                        await _broadcast_progress("ingesting", "Creating sidecars", {
                            "current": i, "total": len(scan.tracks),
                            "step": 1, "total_steps": 1,
                            "step_name": "Creating sidecars",
                        })
                        await asyncio.sleep(0)  # yield so WS messages flush

                total_with_audio = sum(1 for t in scan.tracks if t.audio_exists)

                response = {
                    "total_in_rekordbox": total_with_audio,
                    "already_in_scue": already_in_scue,
                    "queued_for_analysis": len(queued),
                    "sidecars_created": sidecars_created,
                    "sidecars_skipped": sidecars_skipped,
                }

            # ----- Slow path: no prior scan, do everything ----------------
            else:
                from ..layer1.masterdb_scanner import IngestCancelled, ingest_from_master_db

                ingest_phases = [
                    "Reading master.db",
                    "Parsing ANLZ data",
                    "Computing fingerprints",
                ]
                current_phase = {"name": ingest_phases[0], "step": 1}

                def progress_cb(current: int, total: int, message: str) -> None:
                    for i, phase_name in enumerate(ingest_phases):
                        if message == phase_name:
                            current_phase["name"] = phase_name
                            current_phase["step"] = i + 1
                            break
                    asyncio.run_coroutine_threadsafe(
                        _broadcast_progress("ingesting", message, {
                            "current": current,
                            "total": total,
                            "step": current_phase["step"],
                            "total_steps": len(ingest_phases),
                            "step_name": current_phase["name"],
                        }),
                        loop,
                    )

                await _broadcast_progress("ingesting", "Preparing ingest from rekordbox…", {
                    "step": 1, "total_steps": len(ingest_phases), "step_name": ingest_phases[0],
                })

                try:
                    result = await loop.run_in_executor(
                        None,
                        lambda: ingest_from_master_db(
                            store=_store,
                            bpm_min=bpm_min,
                            bpm_max=bpm_max,
                            genre=genre,
                            search=search,
                            progress_cb=progress_cb,
                            cancel_check=_ingest_cancel.is_set,
                        ),
                    )
                except IngestCancelled:
                    logger.info("Ingest cancelled — partial work preserved")
                    await _broadcast_progress("cancelled", "Ingest cancelled")
                    return

                queued = result.queued_for_analysis
                response = {
                    "total_in_rekordbox": result.total_in_rekordbox,
                    "already_in_scue": result.already_in_scue,
                    "queued_for_analysis": len(queued),
                    "sidecars_created": result.sidecars_created,
                    "sidecars_skipped": result.sidecars_skipped,
                }

            # Phase 2: Start batch analysis for new tracks
            # Skipped entirely when metadata_only — sidecars are the only output.
            if queued and not metadata_only:
                from .jobs import create_job
                from .tracks import _run_batch_analysis, _get_cache

                job = create_job(queued)
                cache = _get_cache()
                cache.create_job(
                    job_id=job.job_id,
                    paths=queued,
                    scan_root="",
                    destination_folder="rekordbox",
                    skip_waveform=skip_waveform,
                )
                # Run analysis inline (we're already in a background task)
                await _run_batch_analysis(
                    job=job,
                    skip_waveform=skip_waveform,
                    scan_root="",
                    destination_folder="rekordbox",
                )
                response["job_id"] = job.job_id

            await _broadcast_progress("ingest_complete", "Ingest complete", response)
            logger.info(
                "Ingest complete: %d queued, %d sidecars",
                response["queued_for_analysis"], response["sidecars_created"],
            )

        except Exception as e:
            logger.exception("Background ingest failed: %s", e)
            await _broadcast_progress("error", f"Ingest failed: {e}")
        finally:
            _ingest_in_progress = False


@router.post("/master-db/cancel")
async def cancel_master_db_ingest() -> dict:
    """Cancel an in-progress master.db ingest.

    The running ingest will stop at the next checkpoint and preserve
    any sidecars already created. Returns immediately.
    """
    if not _ingest_lock.locked():
        return {"status": "idle", "message": "No ingest in progress"}
    _ingest_cancel.set()
    logger.info("Ingest cancel requested")
    return {"status": "cancelling", "message": "Cancel signal sent"}
