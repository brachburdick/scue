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

# These will be initialized by the app startup
_store: TrackStore | None = None
_cache: TrackCache | None = None
_tracks_dir: Path | None = None
_cache_path: Path | None = None
_audio_extensions: set[str] = {".mp3", ".wav", ".flac", ".aiff", ".m4a", ".ogg"}
_strata_dir: Path | None = None
_strata_cache: dict[str, set[str]] | None = None  # fingerprint -> set of tier names


def init_tracks_api(
    tracks_dir: Path,
    cache_path: Path,
    audio_extensions: set[str] | None = None,
    strata_dir: Path | None = None,
) -> None:
    """Initialize the tracks API with storage paths.

    Called during app startup.
    """
    global _store, _cache, _tracks_dir, _cache_path, _audio_extensions, _strata_dir
    _tracks_dir = tracks_dir
    _cache_path = cache_path
    _store = TrackStore(tracks_dir)
    _cache = TrackCache(cache_path)
    if audio_extensions is not None:
        _audio_extensions = audio_extensions
    if strata_dir is not None:
        _strata_dir = strata_dir
    logger.info("Tracks API initialized: tracks=%s, cache=%s", tracks_dir, cache_path)


_VALID_TIERS = {"quick", "standard", "deep", "live", "live_offline"}


def _scan_strata() -> dict[str, set[str]]:
    """Scan the strata directory and build a fingerprint → set-of-tiers mapping.

    Parses filenames matching {fp}.{tier}.json or {fp}.{tier}.{source}.json.
    """
    global _strata_cache
    if _strata_cache is not None:
        return _strata_cache

    result: dict[str, set[str]] = {}
    if _strata_dir is None or not _strata_dir.exists():
        _strata_cache = result
        return result

    for path in _strata_dir.glob("*.json"):
        parts = path.stem.split(".")
        if len(parts) == 2:
            fp, tier = parts
        elif len(parts) == 3:
            fp, tier, _source = parts
        else:
            continue
        if tier not in _VALID_TIERS:
            continue
        if fp not in result:
            result[fp] = set()
        result[fp].add(tier)

    _strata_cache = result
    logger.info("Strata scan: %d tracks with analysis data", len(result))
    return result


def invalidate_strata_cache() -> None:
    """Clear the strata availability cache so next request rescans."""
    global _strata_cache
    _strata_cache = None


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

    # Merge strata tier availability
    strata_map = _scan_strata()
    for track in tracks:
        tiers = strata_map.get(track.get("fingerprint", ""), set())
        track["has_quick"] = "quick" in tiers
        track["has_standard"] = "standard" in tiers
        track["has_deep"] = "deep" in tiers
        track["has_live"] = "live" in tiers
        track["has_live_offline"] = "live_offline" in tiers

    return {"tracks": tracks, "total": total}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> dict:
    """Poll the status of a batch analysis job."""
    job = get_job(job_id)
    if job is not None:
        return job_to_dict(job)

    # Fall back to SQLite (for completed/historical jobs)
    cache = _get_cache()
    persisted = cache.get_job(job_id)
    if persisted is None:
        raise HTTPException(404, f"Job not found: {job_id}")

    return {
        "job_id": persisted["job_id"],
        "status": persisted["status"],
        "total": persisted["total"],
        "completed": persisted["completed"],
        "failed": persisted["failed"],
        "current_file": persisted.get("current_file"),
        "current_step": persisted.get("current_step", 0),
        "current_step_name": persisted.get("current_step_name", ""),
        "total_steps": persisted.get("total_steps", 10),
        "results": persisted.get("results", []),
    }


@router.get("/resolve/{source_player}/{source_slot}/{rekordbox_id}")
async def resolve_track(
    source_player: str,
    source_slot: str,
    rekordbox_id: int,
) -> dict:
    """Resolve a composite key (source_player, source_slot, rekordbox_id) to a fingerprint.

    Used by the frontend to look up track analysis from bridge-reported IDs (ADR-015).
    """
    cache = _get_cache()
    fingerprint = cache.lookup_fingerprint(
        rekordbox_id, source_player=source_player, source_slot=source_slot,
    )
    if fingerprint is None:
        raise HTTPException(
            404,
            f"No track linked for {source_player}/{source_slot}/{rekordbox_id}",
        )
    # Include title + artist from cache for quick display before full analysis loads
    track_meta = cache.get_track(fingerprint)
    title = track_meta.get("title", "") if track_meta else ""
    artist = track_meta.get("artist", "") if track_meta else ""
    return {
        "fingerprint": fingerprint,
        "title": title,
        "artist": artist,
    }


@router.get("/{fingerprint}/events")
async def get_track_events(fingerprint: str) -> dict:
    """Get detected events and drum patterns for a track.

    Returns tonal events (riser, faller, stab) as individual objects
    and percussion as compact DrumPattern objects.
    """
    from ..layer1.detectors.events import drum_pattern_to_dict
    from ..layer1.models import event_to_dict

    store = _get_store()
    analysis = store.load_latest(fingerprint)
    if analysis is None:
        raise HTTPException(404, f"Track not found: {fingerprint[:16]}")

    return {
        "fingerprint": fingerprint,
        "events": [event_to_dict(e) for e in analysis.events],
        "drum_patterns": [drum_pattern_to_dict(p) for p in analysis.drum_patterns],
        "total_events": len(analysis.events),
        "total_patterns": len(analysis.drum_patterns),
        "event_types": list(set(e.type for e in analysis.events)),
    }


@router.get("/{fingerprint}/live-data")
async def get_live_data(fingerprint: str) -> dict:
    """Get saved live Pioneer data for a track.

    Returns the captured phrases, beat grid, cue points, etc.
    from a live DJ session.
    """
    store = _get_store()
    data = store.load_live_data(fingerprint)
    if data is None:
        raise HTTPException(404, f"No live data for track: {fingerprint[:16]}")
    return data


@router.get("/{fingerprint}/pioneer-waveform")
async def get_pioneer_waveform(fingerprint: str) -> dict:
    """Get Pioneer ANLZ waveform data for a track.

    Returns decoded PWV5 (color detail), PWV3 (monochrome detail),
    and/or PWV7 (3-band detail) waveform arrays if available from USB scan.

    Waveforms are pre-computed by rekordbox and read from USB ANLZ files.
    This enables instant waveform display before SCUE analysis completes.
    """
    cache = _get_cache()

    # Look up the rekordbox_id → try to find pioneer metadata
    # We need to find which (source_player, source_slot, rekordbox_id) maps to this fingerprint
    pioneer_meta = cache.get_pioneer_waveforms_by_fingerprint(fingerprint)
    if pioneer_meta is None:
        raise HTTPException(404, f"No Pioneer waveform data for track: {fingerprint[:16]}")

    result: dict = {
        "fingerprint": fingerprint,
        "available": [],
    }

    # Decode PWV5: color detail (2 bytes per entry, big-endian u16)
    # Bits: [15:13]=R, [12:10]=G, [9:7]=B, [6:2]=H, [1:0]=unused
    pwv5_bytes = pioneer_meta.get("waveform_pwv5", b"")
    if pwv5_bytes:
        entries = []
        for i in range(0, len(pwv5_bytes) - 1, 2):
            val = (pwv5_bytes[i] << 8) | pwv5_bytes[i + 1]
            entries.append({
                "r": (val >> 13) & 0x07,
                "g": (val >> 10) & 0x07,
                "b": (val >> 7) & 0x07,
                "height": (val >> 2) & 0x1F,
            })
        result["pwv5"] = {
            "entries_per_second": 150,
            "total_entries": len(entries),
            "data": entries,
        }
        result["available"].append("pwv5")

    # Decode PWV3: monochrome detail (1 byte per entry)
    # Bits: [7:5]=intensity, [4:0]=height
    pwv3_bytes = pioneer_meta.get("waveform_pwv3", b"")
    if pwv3_bytes:
        entries = []
        for b in pwv3_bytes:
            entries.append({
                "height": b & 0x1F,
                "intensity": (b >> 5) & 0x07,
            })
        result["pwv3"] = {
            "entries_per_second": 150,
            "total_entries": len(entries),
            "data": entries,
        }
        result["available"].append("pwv3")

    # Decode PWV7: 3-band detail (3 bytes per entry)
    # Bytes: [0]=mid, [1]=high, [2]=low
    pwv7_bytes = pioneer_meta.get("waveform_pwv7", b"")
    if pwv7_bytes:
        entries = []
        for i in range(0, len(pwv7_bytes) - 2, 3):
            entries.append({
                "mid": pwv7_bytes[i],
                "high": pwv7_bytes[i + 1],
                "low": pwv7_bytes[i + 2],
            })
        result["pwv7"] = {
            "entries_per_second": 150,
            "total_entries": len(entries),
            "data": entries,
        }
        result["available"].append("pwv7")

    if not result["available"]:
        raise HTTPException(404, f"No Pioneer waveform data for track: {fingerprint[:16]}")

    return result


# ---------------------------------------------------------------------------
# Settings endpoints (must be before /{fingerprint} catch-all)
# ---------------------------------------------------------------------------


@router.get("/settings/last-scan-path")
async def get_last_scan_path() -> dict:
    """Get the last used scan path and recent paths."""
    import json
    cache = _get_cache()
    last = cache.get_setting("last_scan_path")
    raw = cache.get_setting("recent_scan_paths")
    recent: list[str] = json.loads(raw) if raw else []
    return {"path": last, "recent": recent}


class SetScanPathRequest(BaseModel):
    path: str


@router.put("/settings/last-scan-path")
async def set_last_scan_path(req: SetScanPathRequest) -> dict:
    """Store the last used scan path."""
    cache = _get_cache()
    cache.set_setting("last_scan_path", req.path)
    _update_recent_paths(cache, req.path)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Folder management endpoints (must be before /{fingerprint} catch-all)
# ---------------------------------------------------------------------------


@router.get("/folders")
async def list_folder_contents(
    parent: str = Query(default=""),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at"),
    sort_desc: bool = Query(True),
) -> dict:
    """List folders and tracks at a given directory level.

    Used by the directory view in the frontend.
    """
    cache = _get_cache()
    folders = cache.list_subfolders(parent)
    tracks = cache.list_tracks_in_folder(
        folder=parent, limit=limit, offset=offset,
        sort_by=sort_by, sort_desc=sort_desc,
    )
    track_count = cache.count_tracks_in_folder(parent)
    return {
        "parent": parent,
        "folders": folders,
        "tracks": tracks,
        "track_count": track_count,
    }


class CreateFolderRequest(BaseModel):
    path: str


@router.post("/folders")
async def create_folder(req: CreateFolderRequest) -> dict:
    """Create a virtual folder. Also creates a directory on the filesystem if possible."""
    import json
    folder_path = req.path.strip("/")
    if not folder_path:
        raise HTTPException(400, "Folder path cannot be empty")

    # Store in explicit_folders setting so empty folders are visible
    cache = _get_cache()
    raw = cache.get_setting("explicit_folders")
    folders: list[str] = json.loads(raw) if raw else []
    if folder_path not in folders:
        folders.append(folder_path)
        cache.set_setting("explicit_folders", json.dumps(folders))

    return {"path": folder_path}


class MoveTrackRequest(BaseModel):
    folder: str


@router.patch("/{fingerprint}/folder")
async def move_track_folder(fingerprint: str, req: MoveTrackRequest) -> dict:
    """Move a track to a different virtual folder."""
    store = _get_store()
    cache = _get_cache()

    analysis = store.load_latest(fingerprint)
    if analysis is None:
        raise HTTPException(404, f"Track not found: {fingerprint[:16]}")

    analysis.folder = req.folder.strip("/")
    store.save(analysis)
    cache.index_analysis(analysis)

    return {"fingerprint": fingerprint, "folder": analysis.folder}


# NOTE: /{fingerprint} must come AFTER all fixed-path routes (/jobs, /scan, /resolve,
# /settings, /folders, etc.) to avoid FastAPI matching fixed paths as fingerprint values.
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


def _run_analysis_task(
    audio_path: str,
    force: bool = False,
    skip_waveform: bool = False,
) -> None:
    """Background task for track analysis.

    NOTE: This is a sync function (not async def) so FastAPI runs it in a
    thread pool instead of blocking the event loop.
    """
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
    recursive: bool = True
    destination_folder: str = ""


class BatchAnalyzeRequest(BaseModel):
    paths: list[str]
    skip_waveform: bool = False
    scan_root: str = ""
    destination_folder: str = ""


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
        if target.suffix.lower() not in _audio_extensions:
            raise HTTPException(400, f"Not an audio file: {target.name}")
        audio_files = [target]
    elif req.recursive:
        audio_files = sorted(
            f for f in target.rglob("*")
            if f.is_file() and f.suffix.lower() in _audio_extensions
        )
    else:
        audio_files = sorted(
            f for f in target.iterdir()
            if f.is_file() and f.suffix.lower() in _audio_extensions
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

    # Persist last scan path
    cache = _get_cache()
    cache.set_setting("last_scan_path", req.path)
    _update_recent_paths(cache, req.path)

    return {
        "path": req.path,
        "scan_root": str(target),
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

    # Persist job to SQLite for resume support
    cache = _get_cache()
    cache.create_job(
        job_id=job.job_id,
        paths=req.paths,
        scan_root=req.scan_root,
        destination_folder=req.destination_folder,
        skip_waveform=req.skip_waveform,
    )

    background_tasks.add_task(
        _run_batch_analysis,
        job=job,
        skip_waveform=req.skip_waveform,
        scan_root=req.scan_root,
        destination_folder=req.destination_folder,
    )

    return {"job_id": job.job_id}


async def _run_batch_analysis(
    job: AnalysisJob,
    skip_waveform: bool = False,
    scan_root: str = "",
    destination_folder: str = "",
) -> None:
    """Background task that processes batch analysis sequentially."""
    from ..layer1.analysis import run_analysis
    from ..layer1.fingerprint import compute_fingerprint

    job.status = "running"
    cache = _get_cache()
    store = _get_store()
    cache.update_job_progress(job.job_id, status="running")

    def _make_progress_cb(j: AnalysisJob):
        """Create a progress callback that updates the job's per-step fields."""
        def cb(step: int, step_name: str, total_steps: int) -> None:
            j.current_step = step
            j.current_step_name = step_name
            j.total_steps = total_steps
            cache.update_job_progress(
                j.job_id,
                current_step=step,
                current_step_name=step_name,
                total_steps=total_steps,
            )
        return cb

    for i, file_result in enumerate(job.results):
        if file_result.status != "pending":
            continue  # skip already-processed files (for resume)

        job.current_file = file_result.filename
        job.current_step = 0
        job.current_step_name = "Starting"
        cache.update_job_progress(
            job.job_id, current_file=file_result.filename,
            current_step=0, current_step_name="Starting",
        )
        try:
            await asyncio.to_thread(
                run_analysis,
                audio_path=file_result.path,
                tracks_dir=_tracks_dir,
                cache_path=_cache_path,
                skip_waveform=skip_waveform,
                progress_callback=_make_progress_cb(job),
            )
            file_result.status = "done"
            file_result.fingerprint = compute_fingerprint(Path(file_result.path))
            job.completed += 1

            # Compute and assign folder
            folder = _compute_folder(file_result.path, scan_root, destination_folder)
            if folder:
                analysis = store.load(file_result.fingerprint)
                if analysis and analysis.folder != folder:
                    analysis.folder = folder
                    store.save(analysis)
                    cache.index_analysis(analysis)

            cache.update_job_file(job.job_id, i, "done", file_result.fingerprint)
            cache.update_job_progress(
                job.job_id, completed=job.completed, failed=job.failed,
            )
            logger.info("Batch [%d/%d] done: %s", i + 1, job.total, file_result.filename)
        except Exception as exc:
            logger.exception("Batch [%d/%d] failed: %s", i + 1, job.total, file_result.filename)
            file_result.status = "error"
            file_result.error = f"{type(exc).__name__}: {exc}"
            job.failed += 1
            cache.update_job_file(
                job.job_id, i, "error", error=f"{type(exc).__name__}: {exc}",
            )
            cache.update_job_progress(
                job.job_id, completed=job.completed, failed=job.failed,
            )

    job.current_file = None
    if job.failed > 0:
        job.status = "complete_with_errors"
    else:
        job.status = "complete"
    cache.update_job_progress(job.job_id, status=job.status, current_file="")
    logger.info("Batch job %s finished: %d/%d succeeded", job.job_id, job.completed, job.total)


def _compute_folder(file_path: str, scan_root: str, destination_folder: str) -> str:
    """Compute the virtual folder for an analyzed file.

    Preserves the source directory structure relative to the scan root.
    Example: scan_root="/Music/techno", file="/Music/techno/dark/track.mp3",
             destination="artist1" → "artist1/techno/dark"
    """
    if not scan_root:
        return destination_folder

    file_dir = str(Path(file_path).parent)
    scan_root_parent = str(Path(scan_root).parent)

    # Get relative path from scan root's parent (keeping the scan root dir name)
    if file_dir.startswith(scan_root_parent):
        relative = file_dir[len(scan_root_parent):].strip("/")
    else:
        relative = Path(file_path).parent.name

    if destination_folder:
        return f"{destination_folder}/{relative}" if relative else destination_folder
    return relative


def _update_recent_paths(cache: TrackCache, path: str) -> None:
    """Update the list of recent scan paths (keeps last 5)."""
    import json
    raw = cache.get_setting("recent_scan_paths")
    recent: list[str] = json.loads(raw) if raw else []
    if path in recent:
        recent.remove(path)
    recent.insert(0, path)
    recent = recent[:5]
    cache.set_setting("recent_scan_paths", json.dumps(recent))


# ---------------------------------------------------------------------------
# Job resume on startup
# ---------------------------------------------------------------------------


async def resume_incomplete_jobs() -> None:
    """Resume any incomplete analysis jobs from a previous session.

    Called during app startup after init_tracks_api().
    """
    cache = _get_cache()
    incomplete = cache.get_incomplete_jobs()

    for job_data in incomplete:
        job_id = job_data["job_id"]
        pending_files = cache.get_job_pending_files(job_id)
        if not pending_files:
            # All files were processed; mark complete
            cache.update_job_progress(job_id, status="complete")
            continue

        logger.info(
            "Resuming job %s: %d files remaining",
            job_id, len(pending_files),
        )

        # Reconstruct in-memory job
        from .jobs import AnalysisJob, FileResult
        paths = [f["path"] for f in pending_files]
        results = [
            FileResult(path=f["path"], filename=f["filename"])
            for f in pending_files
        ]

        all_files = cache.get_job(job_id)
        total = all_files["total"] if all_files else len(pending_files)

        job = AnalysisJob(
            job_id=job_id,
            total=total,
            completed=job_data.get("completed", 0),
            failed=job_data.get("failed", 0),
            results=results,
        )

        # Register in the in-memory store
        from .jobs import _jobs
        _jobs[job_id] = job

        # Spawn background task
        import asyncio
        asyncio.create_task(
            _run_batch_analysis(
                job=job,
                skip_waveform=bool(job_data.get("skip_waveform", 0)),
                scan_root=job_data.get("scan_root", ""),
                destination_folder=job_data.get("destination_folder", ""),
            )
        )


class RecomputeWaveformRequest(BaseModel):
    low_crossover: int = 200
    high_crossover: int = 2500


@router.post("/{fingerprint}/recompute-waveform")
async def recompute_waveform(fingerprint: str, req: RecomputeWaveformRequest) -> dict:
    """Recompute waveform with custom frequency crossovers.

    The original analysis uses fixed crossovers (20-200-2500 Hz).
    This endpoint re-runs the STFT band extraction with custom boundaries
    and updates the stored analysis.
    """
    store = _get_store()
    analysis = store.load(fingerprint)
    if analysis is None:
        raise HTTPException(404, f"Track not found: {fingerprint[:16]}")

    if not analysis.audio_path:
        raise HTTPException(400, "No audio path stored for this track")

    audio_path = Path(analysis.audio_path)
    if not audio_path.exists():
        raise HTTPException(400, f"Audio file not found: {audio_path}")

    import librosa
    from ..layer1.waveform import compute_rgb_waveform

    signal, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    waveform = compute_rgb_waveform(
        signal, sr,
        low_band=(20, req.low_crossover),
        mid_band=(req.low_crossover, req.high_crossover),
        high_band=(req.high_crossover, sr // 2),
    )

    analysis.waveform = waveform
    store.save(analysis)
    logger.info(
        "Recomputed waveform for %s with crossovers %d/%d Hz",
        fingerprint[:16], req.low_crossover, req.high_crossover,
    )

    return {
        "fingerprint": fingerprint,
        "status": "recomputed",
        "low_crossover": req.low_crossover,
        "high_crossover": req.high_crossover,
        "frames": len(waveform.low),
    }
