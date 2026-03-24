"""REST API endpoints for Strata arrangement analysis.

- GET  /api/strata                              — list tracks with strata data
- GET  /api/tracks/{fp}/strata                  — get all tier+source results
- GET  /api/tracks/{fp}/strata/{tier}           — get tier result (optional source param)
- PUT  /api/tracks/{fp}/strata/{tier}           — save edited arrangement
- POST /api/tracks/{fp}/strata/analyze          — trigger strata analysis
- DELETE /api/tracks/{fp}/strata/{tier}          — delete tier result
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

logger = logging.getLogger(__name__)

router = APIRouter(tags=["strata"])

_store: StrataStore | None = None
_tracks_dir: Path | None = None
_cache_path: Path | None = None


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
    return {"ok": True, "tier": tier, "source": req.source}


class AnalyzeStrataRequest(BaseModel):
    tiers: list[str] = ["quick", "standard"]
    analysis_source: str | None = None


def _run_strata_analysis(
    fingerprint: str, tiers: list[str], analysis_version: int | None = None,
) -> None:
    """Run strata analysis in a background thread.

    Defined as a plain function (not async) so FastAPI runs it in
    the thread pool, avoiding event loop blocking.
    """
    from ..layer1.strata.engine import StrataEngine

    store = _get_store()
    if _tracks_dir is None:
        logger.error("Tracks dir not configured for strata analysis")
        return

    engine = StrataEngine(tracks_dir=_tracks_dir, strata_store=store)
    try:
        results = engine.analyze(fingerprint, tiers, analysis_version=analysis_version)
        logger.info("Strata analysis complete for %s: %s",
                     fingerprint[:16], list(results.keys()))
    except Exception:
        logger.exception("Strata analysis failed for %s", fingerprint[:16])


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

    # For quick tier, run synchronously (fast enough at ~3-7s)
    if req.tiers == ["quick"]:
        from ..layer1.strata.engine import StrataEngine
        store = _get_store()
        engine = StrataEngine(tracks_dir=_tracks_dir, strata_store=store)
        try:
            results = engine.analyze(fingerprint, req.tiers, analysis_version=analysis_version)
            return {
                "fingerprint": fingerprint,
                "completed_tiers": list(results.keys()),
                "analysis_source": req.analysis_source or "latest",
                "status": "complete",
            }
        except ValueError as e:
            raise HTTPException(404, str(e))
        except Exception as e:
            logger.exception("Quick strata analysis failed")
            raise HTTPException(500, f"Analysis failed: {e}")

    # For standard/deep tiers, run in background
    background_tasks.add_task(_run_strata_analysis, fingerprint, req.tiers, analysis_version)
    return {
        "fingerprint": fingerprint,
        "requested_tiers": req.tiers,
        "analysis_source": req.analysis_source or "latest",
        "status": "started",
        "message": "Analysis started. Poll GET /api/tracks/{fp}/strata for results.",
    }


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
