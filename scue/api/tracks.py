"""REST API endpoints for track management.

Provides CRUD operations for track analyses:
- GET /api/tracks — list all analyzed tracks (from SQLite cache)
- GET /api/tracks/{fingerprint} — get full analysis (from JSON)
- POST /api/tracks/analyze — trigger analysis of an audio file
- POST /api/tracks/scan — scan a directory for audio files
- POST /api/tracks/analyze-batch — batch analyze multiple files
- GET /api/tracks/jobs/{job_id} — poll batch analysis progress
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from ..layer1.models import analysis_to_dict
from ..layer1.storage import TrackCache, TrackStore
from .jobs import AnalysisJob, create_job, get_job, job_to_dict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tracks", tags=["tracks"])

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aiff", ".m4a", ".ogg"}

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


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> dict:
    """Poll the status of a batch analysis job."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, f"Job not found: {job_id}")
    return job_to_dict(job)


# NOTE: /{fingerprint} must come AFTER all fixed-path routes (/jobs, /scan, etc.)
# to avoid FastAPI matching "jobs" or "scan" as a fingerprint value.
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


# ---------------------------------------------------------------------------
# Scan & Batch Analyze (FE-4)
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    path: str


class BatchAnalyzeRequest(BaseModel):
    paths: list[str]
    skip_waveform: bool = False


@router.post("/scan")
async def scan_directory(req: ScanRequest) -> dict:
    """Scan a directory (or single file) for audio files.

    Returns which files are new vs already analyzed.
    """
    from ..layer1.fingerprint import compute_fingerprint

    target = Path(req.path)
    if not target.exists():
        raise HTTPException(400, f"Path not found: {req.path}")

    # Collect audio files
    if target.is_file():
        if target.suffix.lower() not in AUDIO_EXTENSIONS:
            raise HTTPException(400, f"Not an audio file: {target.name}")
        audio_files = [target]
    else:
        audio_files = sorted(
            f for f in target.iterdir()
            if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
        )

    store = _get_store()
    new_files = []
    already_analyzed = 0

    for f in audio_files:
        fp = compute_fingerprint(f)
        if store.exists(fp):
            already_analyzed += 1
        else:
            new_files.append({"path": str(f), "filename": f.name})

    return {
        "path": req.path,
        "total_files": len(audio_files),
        "already_analyzed": already_analyzed,
        "new_files": new_files,
    }


@router.post("/analyze-batch")
async def analyze_batch(
    req: BatchAnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Start batch analysis of multiple audio files.

    Returns a job_id for polling progress via GET /api/tracks/jobs/{job_id}.
    """
    if not req.paths:
        raise HTTPException(400, "No paths provided")

    # Validate all paths exist
    for p in req.paths:
        if not Path(p).exists():
            raise HTTPException(400, f"Audio file not found: {p}")

    job = create_job(req.paths)
    background_tasks.add_task(
        _run_batch_analysis,
        job=job,
        skip_waveform=req.skip_waveform,
    )

    return {"job_id": job.job_id}


async def _run_batch_analysis(
    job: AnalysisJob,
    skip_waveform: bool = False,
) -> None:
    """Background task that processes batch analysis sequentially."""
    from ..layer1.analysis import run_analysis

    job.status = "running"

    for i, file_result in enumerate(job.results):
        job.current_file = file_result.filename
        try:
            await asyncio.to_thread(
                run_analysis,
                audio_path=file_result.path,
                tracks_dir=_tracks_dir,
                cache_path=_cache_path,
                skip_waveform=skip_waveform,
            )
            file_result.status = "done"
            # Get the fingerprint for the result
            from ..layer1.fingerprint import compute_fingerprint
            file_result.fingerprint = compute_fingerprint(Path(file_result.path))
            job.completed += 1
            logger.info("Batch [%d/%d] done: %s", i + 1, job.total, file_result.filename)
        except Exception:
            logger.exception("Batch [%d/%d] failed: %s", i + 1, job.total, file_result.filename)
            file_result.status = "error"
            file_result.error = "Analysis failed"
            job.failed += 1

    job.current_file = None
    job.status = "complete" if job.failed == 0 else "failed"
    logger.info("Batch job %s finished: %d/%d succeeded", job.job_id, job.completed, job.total)
