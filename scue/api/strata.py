"""REST API endpoints for Strata arrangement analysis.

- GET  /api/strata                              — list tracks with strata data
- GET  /api/tracks/{fp}/strata                  — get all tier+source results
- GET  /api/tracks/{fp}/strata/{tier}           — get tier result (optional source param)
- PUT  /api/tracks/{fp}/strata/{tier}           — save edited arrangement
- POST /api/tracks/{fp}/strata/analyze          — trigger strata analysis
- DELETE /api/tracks/{fp}/strata/{tier}          — delete tier result
- GET  /api/strata/jobs/{job_id}                — poll strata job status
- POST /api/strata/analyze-batch                — batch multi-track strata analysis
- GET  /api/strata/batch/{batch_id}             — poll batch job status
- POST /api/tracks/{fp}/reanalyze               — trigger Pioneer beatgrid re-analysis
- GET  /api/tracks/{fp}/versions                — list TrackAnalysis versions
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from ..layer1.strata.models import formula_from_dict, formula_to_dict
from ..layer1.strata.storage import DEFAULT_SOURCE, VALID_SOURCES, VALID_TIERS, StrataStore
from .tracks import invalidate_strata_cache
from .strata_jobs import (
    StrataBatchJob,
    StrataJob,
    create_strata_batch,
    create_strata_job,
    get_strata_batch,
    get_strata_job,
    strata_batch_to_dict,
    strata_job_to_dict,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["strata"])

_store: StrataStore | None = None
_tracks_dir: Path | None = None
_cache_path: Path | None = None
_tracker: object | None = None  # PlaybackTracker, set by main.py


def init_strata_api(
    store: StrataStore,
    tracks_dir: Path | None = None,
    cache_path: Path | None = None,
) -> None:
    """Initialize the strata API with a storage instance."""
    global _store, _tracks_dir, _cache_path
    _store = store
    _tracks_dir = tracks_dir
    _cache_path = cache_path
    logger.info("Strata API initialized: %s", store.base_dir)


def set_strata_tracker(tracker: object) -> None:
    """Set the PlaybackTracker reference for live strata access."""
    global _tracker
    _tracker = tracker


def _get_store() -> StrataStore:
    if _store is None:
        raise HTTPException(500, "Strata store not initialized")
    return _store


@router.get("/api/strata")
async def list_strata_tracks() -> dict:
    """List all tracks that have strata analysis data."""
    store = _get_store()
    tracks = store.list_tracks()
    return {"tracks": tracks}


@router.get("/api/tracks/{fingerprint}/strata")
async def get_all_strata(fingerprint: str) -> dict:
    """Get all available tier + source results for a track.

    Returns nested structure: {tier: {source: formula}}.
    """
    store = _get_store()
    results = store.load_all(fingerprint)
    if not results:
        raise HTTPException(404, f"No strata data for track: {fingerprint[:16]}")

    tiers_dict: dict[str, dict[str, dict]] = {}
    available_tiers: list[str] = []
    for tier, sources in results.items():
        tiers_dict[tier] = {
            source: formula_to_dict(formula)
            for source, formula in sources.items()
        }
        available_tiers.append(tier)

    return {
        "fingerprint": fingerprint,
        "tiers": tiers_dict,
        "available_tiers": available_tiers,
    }


@router.get("/api/tracks/{fingerprint}/strata/{tier}")
async def get_strata_tier(
    fingerprint: str,
    tier: str,
    source: str = Query(DEFAULT_SOURCE, description="Analysis source"),
) -> dict:
    """Get a specific tier + source arrangement formula."""
    if tier not in VALID_TIERS:
        raise HTTPException(400, f"Invalid tier: {tier!r} (expected one of {list(VALID_TIERS)})")
    if source not in VALID_SOURCES:
        raise HTTPException(400, f"Invalid source: {source!r} (expected one of {list(VALID_SOURCES)})")
    store = _get_store()
    formula = store.load(fingerprint, tier, source)
    if formula is None:
        raise HTTPException(404, f"No {tier}/{source} strata for track: {fingerprint[:16]}")
    return {
        "fingerprint": fingerprint,
        "tier": tier,
        "source": source,
        "formula": formula_to_dict(formula),
    }


class SaveStrataRequest(BaseModel):
    formula: dict
    source: str = DEFAULT_SOURCE


@router.put("/api/tracks/{fingerprint}/strata/{tier}")
async def save_strata_tier(fingerprint: str, tier: str, req: SaveStrataRequest) -> dict:
    """Save or overwrite a tier's arrangement formula (for human corrections)."""
    if tier not in VALID_TIERS:
        raise HTTPException(400, f"Invalid tier: {tier!r} (expected one of {list(VALID_TIERS)})")
    store = _get_store()
    try:
        formula = formula_from_dict(req.formula)
    except (KeyError, TypeError) as e:
        raise HTTPException(400, f"Invalid formula data: {e}")
    if formula.fingerprint != fingerprint:
        raise HTTPException(400, "Formula fingerprint does not match URL")
    store.save(formula, tier, source=req.source)
    invalidate_strata_cache()
    return {"ok": True, "tier": tier, "source": req.source}


class AnalyzeStrataRequest(BaseModel):
    tiers: list[str] = ["quick", "standard"]
    analysis_source: str | None = None


def _run_strata_analysis(
    fingerprint: str,
    tiers: list[str],
    analysis_version: int | None = None,
    job: StrataJob | None = None,
) -> None:
    """Run strata analysis in a background thread.

    Defined as a plain function (not async) so FastAPI runs it in
    the thread pool, avoiding event loop blocking.
    """
    from ..layer1.strata.engine import StrataEngine

    store = _get_store()
    if _tracks_dir is None:
        logger.error("Tracks dir not configured for strata analysis")
        if job:
            job.status = "failed"
            job.error = "Tracks directory not configured"
        return

    if job:
        job.status = "running"

    def _progress(step: int, name: str) -> None:
        if job:
            if job.cancelled:
                raise InterruptedError("Cancelled by user")
            job.current_step = step
            job.current_step_name = name

    engine = StrataEngine(tracks_dir=_tracks_dir, strata_store=store)
    try:
        results = engine.analyze(
            fingerprint, tiers,
            analysis_version=analysis_version,
            progress_callback=_progress,
        )
        invalidate_strata_cache()
        logger.info("Strata analysis complete for %s: %s",
                     fingerprint[:16], list(results.keys()))
        if job:
            job.status = "complete"
            job.current_step = job.total_steps
            job.current_step_name = "Complete"
    except InterruptedError:
        logger.info("Strata analysis cancelled for %s", fingerprint[:16])
        if job and job.status != "failed":
            job.status = "failed"
            job.error = "Cancelled by user"
    except Exception as exc:
        logger.exception("Strata analysis failed for %s", fingerprint[:16])
        if job:
            job.status = "failed"
            job.error = str(exc)


# Map source names to TrackAnalysis version numbers
_SOURCE_TO_VERSION: dict[str, int] = {
    "analysis": 1,
    "pioneer_enriched": 2,
    "pioneer_reanalyzed": 3,
}


@router.post("/api/tracks/{fingerprint}/strata/analyze")
async def analyze_strata(
    fingerprint: str,
    req: AnalyzeStrataRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Trigger strata analysis for a track.

    Optionally specify analysis_source to run Strata on a specific
    TrackAnalysis version (e.g., "pioneer_reanalyzed" for v3).
    """
    invalid = [t for t in req.tiers if t not in VALID_TIERS]
    if invalid:
        raise HTTPException(400, f"Invalid tier(s): {invalid}")

    if _tracks_dir is None:
        raise HTTPException(500, "Tracks directory not configured")

    # Resolve analysis version from source name
    analysis_version = None
    if req.analysis_source:
        if req.analysis_source not in VALID_SOURCES:
            raise HTTPException(400, f"Invalid analysis_source: {req.analysis_source!r}")
        analysis_version = _SOURCE_TO_VERSION.get(req.analysis_source)

    # For quick or live_offline tier, run synchronously (fast enough)
    if req.tiers == ["quick"] or req.tiers == ["live_offline"]:
        from ..layer1.strata.engine import StrataEngine
        store = _get_store()
        engine = StrataEngine(tracks_dir=_tracks_dir, strata_store=store)
        try:
            results = engine.analyze(fingerprint, req.tiers, analysis_version=analysis_version)
            invalidate_strata_cache()
            return {
                "fingerprint": fingerprint,
                "completed_tiers": list(results.keys()),
                "requested_tiers": req.tiers,
                "analysis_source": req.analysis_source or "latest",
                "status": "complete",
            }
        except ValueError as e:
            raise HTTPException(404, str(e))
        except Exception as e:
            logger.exception("Quick strata analysis failed")
            raise HTTPException(500, f"Analysis failed: {e}")

    # Deep tier is not yet implemented
    if req.tiers == ["deep"]:
        return {
            "fingerprint": fingerprint,
            "requested_tiers": req.tiers,
            "status": "not_implemented",
            "message": "Deep tier analysis is not yet available (Phase 6).",
        }

    # For standard/deep tiers, create a tracked job and run in background
    # Determine the primary tier for the job (first non-quick tier)
    primary_tier = next((t for t in req.tiers if t != "quick"), req.tiers[0])
    job = create_strata_job(fingerprint, primary_tier)
    background_tasks.add_task(
        _run_strata_analysis, fingerprint, req.tiers, analysis_version, job,
    )
    return {
        "fingerprint": fingerprint,
        "requested_tiers": req.tiers,
        "analysis_source": req.analysis_source or "latest",
        "status": "started",
        "job_id": job.job_id,
        "message": "Analysis started. Poll GET /api/strata/jobs/{job_id} for progress.",
    }


@router.get("/api/strata/jobs/{job_id}")
async def get_strata_job_status(job_id: str) -> dict:
    """Poll the status of a strata analysis job."""
    job = get_strata_job(job_id)
    if job is None:
        raise HTTPException(404, f"No strata job: {job_id}")
    return strata_job_to_dict(job)


@router.post("/api/strata/jobs/{job_id}/cancel")
async def cancel_strata_job(job_id: str) -> dict:
    """Request cooperative cancellation of a strata analysis job.

    Sets the cancelled flag on the job. The engine checks this between stages
    and stops early. Already-complete or failed jobs are unaffected.
    """
    job = get_strata_job(job_id)
    if job is None:
        raise HTTPException(404, f"No strata job: {job_id}")
    if job.status in ("complete", "failed"):
        return {"ok": True, "status": job.status, "message": "Job already finished"}
    job.cancelled = True
    job.status = "failed"
    job.error = "Cancelled by user"
    return {"ok": True, "status": "cancelled"}


class BatchAnalyzeRequest(BaseModel):
    fingerprints: list[str]
    tiers: list[str] = ["quick"]


@router.post("/api/strata/analyze-batch")
async def analyze_strata_batch(
    req: BatchAnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Trigger strata analysis for multiple tracks.

    Creates a batch job and runs analysis sequentially in the background.
    """
    invalid = [t for t in req.tiers if t not in VALID_TIERS]
    if invalid:
        raise HTTPException(400, f"Invalid tier(s): {invalid}")
    if not req.fingerprints:
        raise HTTPException(400, "No fingerprints provided")
    if _tracks_dir is None:
        raise HTTPException(500, "Tracks directory not configured")

    batch = create_strata_batch(req.fingerprints, req.tiers)
    background_tasks.add_task(_run_strata_batch, batch)
    return strata_batch_to_dict(batch)


@router.get("/api/strata/batch/{batch_id}")
async def get_strata_batch_status(batch_id: str) -> dict:
    """Poll the status of a strata batch job."""
    batch = get_strata_batch(batch_id)
    if batch is None:
        raise HTTPException(404, f"No strata batch: {batch_id}")
    return strata_batch_to_dict(batch)


def _run_strata_batch(batch: StrataBatchJob) -> None:
    """Run batch strata analysis sequentially in background."""
    batch.status = "running"
    for job in batch.jobs:
        _run_strata_analysis(job.fingerprint, [job.tier], job=job)
    invalidate_strata_cache()
    # Determine overall status
    if all(j.status == "complete" for j in batch.jobs):
        batch.status = "complete"
    elif any(j.status == "failed" for j in batch.jobs):
        batch.status = "complete"  # partial success is still "complete"
    else:
        batch.status = "failed"


@router.delete("/api/tracks/{fingerprint}/strata/{tier}")
async def delete_strata_tier(
    fingerprint: str,
    tier: str,
    source: str = Query(DEFAULT_SOURCE, description="Analysis source"),
) -> dict:
    """Delete a specific tier + source strata data."""
    if tier not in VALID_TIERS:
        raise HTTPException(400, f"Invalid tier: {tier!r} (expected one of {list(VALID_TIERS)})")
    store = _get_store()
    deleted = store.delete(fingerprint, tier, source)
    if not deleted:
        raise HTTPException(404, f"No {tier}/{source} strata for track: {fingerprint[:16]}")
    invalidate_strata_cache()
    return {"ok": True, "tier": tier, "source": source}


# ---------------------------------------------------------------------------
# Reanalysis & Version endpoints
# ---------------------------------------------------------------------------

def _run_reanalysis(fingerprint: str) -> None:
    """Run reanalysis in a background thread."""
    from ..layer1.reanalysis import run_reanalysis_pass
    from ..layer1.storage import TrackCache, TrackStore

    if _tracks_dir is None:
        logger.error("Tracks dir not configured for reanalysis")
        return

    store = TrackStore(_tracks_dir)
    cache = TrackCache(_cache_path) if _cache_path else TrackCache(":memory:")

    # Load the enriched analysis (v2)
    enriched = store.load(fingerprint, version=2)
    if enriched is None:
        logger.error("No enriched analysis (v2) found for %s", fingerprint[:16])
        return

    audio_path = Path(enriched.audio_path)
    try:
        run_reanalysis_pass(enriched, audio_path, store, cache)
    except Exception:
        logger.exception("Reanalysis failed for %s", fingerprint[:16])


@router.post("/api/tracks/{fingerprint}/reanalyze")
async def reanalyze_track(
    fingerprint: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """Trigger re-analysis with Pioneer beatgrid.

    Requires an enriched analysis (v2, source="pioneer_enriched") to exist.
    Produces a v3 analysis with source="pioneer_reanalyzed".
    Runs as a background task (~5-10s for audio feature extraction).
    """
    if _tracks_dir is None:
        raise HTTPException(500, "Tracks directory not configured")

    from ..layer1.storage import TrackStore
    store = TrackStore(_tracks_dir)

    # Check v2 exists
    enriched = store.load(fingerprint, version=2)
    if enriched is None:
        raise HTTPException(
            404,
            f"No enriched analysis (v2) for {fingerprint[:16]}. "
            "Run Pioneer enrichment first.",
        )

    # Check v3 doesn't already exist
    existing_v3 = store.load(fingerprint, version=3)
    if existing_v3 is not None:
        return {
            "fingerprint": fingerprint,
            "status": "already_exists",
            "version": 3,
            "source": existing_v3.source,
        }

    background_tasks.add_task(_run_reanalysis, fingerprint)
    return {
        "fingerprint": fingerprint,
        "status": "started",
        "message": "Re-analysis started. Poll GET /api/tracks/{fp}/versions to check.",
    }


@router.get("/api/tracks/{fingerprint}/versions")
async def list_track_versions(fingerprint: str) -> dict:
    """List all TrackAnalysis versions for a track."""
    if _tracks_dir is None:
        raise HTTPException(500, "Tracks directory not configured")

    from ..layer1.storage import TrackStore
    store = TrackStore(_tracks_dir)

    versions: list[dict] = []
    for v in range(1, 11):
        analysis = store.load(fingerprint, version=v)
        if analysis is not None:
            versions.append({
                "version": analysis.version,
                "source": analysis.source,
                "beatgrid_source": analysis.beatgrid_source,
                "n_sections": len(analysis.sections),
                "n_events": len(analysis.events),
                "n_drum_patterns": len(analysis.drum_patterns),
                "bpm": analysis.bpm,
                "created_at": analysis.created_at,
            })

    if not versions:
        raise HTTPException(404, f"No analysis found for {fingerprint[:16]}")

    return {
        "fingerprint": fingerprint,
        "versions": versions,
    }


@router.get("/api/strata/live")
async def get_live_strata() -> dict:
    """Get current live strata formulas from all active players.

    Returns per-player arrangement formulas built from Pioneer hardware data.
    These are constructed in real-time from phrase analysis, beat grid,
    waveform, and cue point data streaming from the hardware.
    """
    if _tracker is None:
        return {"players": {}}

    from ..layer1.tracking import PlaybackTracker
    tracker: PlaybackTracker = _tracker  # type: ignore[assignment]

    result: dict[str, dict] = {}
    # Check all possible player numbers (1-4 for Pioneer)
    for pn in range(1, 5):
        formula = tracker.get_live_strata(pn)
        if formula is not None:
            result[str(pn)] = formula_to_dict(formula)

    return {"players": result}
