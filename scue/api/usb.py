"""USB scanning API — scan Pioneer USB sticks and link tracks to SCUE analyses.

Pre-set preparation: scan exportLibrary.db from a USB, match tracks to
existing analyses, and cache Pioneer metadata for enrichment during the set.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config.loader import UsbConfig
from ..layer1.storage import TrackCache, TrackStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/usb", tags=["usb"])

# Set by main.py at startup
_store: TrackStore | None = None
_cache: TrackCache | None = None
_last_scan: dict | None = None
_usb_config = UsbConfig()  # defaults until init_usb_api() is called


def init_usb_api(
    store: TrackStore,
    cache: TrackCache,
    usb_config: UsbConfig | None = None,
) -> None:
    """Store references for the USB endpoints."""
    global _store, _cache, _usb_config
    _store = store
    _cache = cache
    if usb_config is not None:
        _usb_config = usb_config


class UsbScanRequest(BaseModel):
    """Request body for POST /api/usb/scan."""
    path: str  # Path to USB root directory (or directly to exportLibrary.db)


@router.post("/scan")
async def scan_usb(req: UsbScanRequest) -> dict:
    """Scan a Pioneer USB stick and link tracks to existing SCUE analyses.

    Accepts either:
    - Path to USB root (e.g., /Volumes/SKALD) — will look for PIONEER/rekordbox/exportLibrary.db
    - Direct path to exportLibrary.db

    Returns scan results: matched, unmatched, already_linked counts.
    """
    global _last_scan

    if _store is None or _cache is None:
        raise HTTPException(status_code=500, detail="USB API not initialized")

    # Lazy import to keep rbox optional
    try:
        from ..layer1.usb_scanner import (
            apply_scan_results,
            match_usb_tracks,
            read_usb_library,
        )
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"USB scanning dependencies not installed: {e}. "
                   f"Install with: pip install 'scue[usb]' "
                   f"(rbox for database reading, pyrekordbox for ANLZ parsing)",
        )

    usb_path = Path(req.path)

    # Resolve paths
    if usb_path.name == "exportLibrary.db":
        db_path = usb_path
        anlz_dir = usb_path.parent.parent.parent / "USBANLZ"
    elif (usb_path / _usb_config.db_relative_path).exists():
        db_path = usb_path / _usb_config.db_relative_path
        anlz_dir = usb_path / _usb_config.anlz_relative_path
    else:
        raise HTTPException(
            status_code=400,
            detail=f"No exportLibrary.db found at {usb_path}. "
                   f"Provide a path to the USB root or directly to exportLibrary.db.",
        )

    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Database not found: {db_path}")

    # Read, match, and apply
    usb_tracks = read_usb_library(db_path, anlz_dir if anlz_dir.exists() else None)

    result = match_usb_tracks(usb_tracks, _cache, _store)
    result.usb_path = str(usb_path)

    linked = apply_scan_results(result, _cache)

    # Cache last scan for status endpoint
    _last_scan = {
        "usb_path": result.usb_path,
        "total_tracks": result.total_tracks,
        "matched": len(result.matched),
        "unmatched": len(result.unmatched),
        "already_linked": result.already_linked,
        "newly_linked": linked,
        "scan_timestamp": result.scan_timestamp,
        "matched_tracks": [
            {
                "rekordbox_id": m.usb_track.rekordbox_id,
                "title": m.usb_track.title,
                "artist": m.usb_track.artist,
                "fingerprint": m.fingerprint[:12],
                "match_method": m.match_method,
            }
            for m in result.matched
        ],
        "unmatched_tracks": [
            {
                "rekordbox_id": t.rekordbox_id,
                "title": t.title,
                "artist": t.artist,
            }
            for t in result.unmatched[:50]  # Limit to 50 for response size
        ],
    }

    return _last_scan


@router.get("/status")
async def usb_status() -> dict:
    """Return the result of the last USB scan."""
    if _last_scan is None:
        return {"status": "no_scan", "message": "No USB has been scanned yet."}
    return _last_scan


@router.get("/pioneer-metadata")
async def list_pioneer_metadata() -> dict:
    """List all cached Pioneer metadata from USB scans."""
    if _cache is None:
        raise HTTPException(status_code=500, detail="USB API not initialized")

    metadata = _cache.list_pioneer_metadata()
    return {
        "count": len(metadata),
        "tracks": metadata,
    }
