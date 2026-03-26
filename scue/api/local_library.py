"""Local rekordbox library API — scan and match local ANLZ files.

Endpoints for detecting, scanning, and querying the local rekordbox
library without requiring Pioneer hardware.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..layer1.storage import TrackCache, TrackStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/local-library", tags=["local-library"])

# Set by main.py at startup
_store: TrackStore | None = None
_cache: TrackCache | None = None
_last_scan: dict | None = None


def init_local_library_api(store: TrackStore, cache: TrackCache) -> None:
    """Store references for the local library endpoints."""
    global _store, _cache
    _store = store
    _cache = cache


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
