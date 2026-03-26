"""REST API for the track scanner (bridge command channel).

Endpoints for browsing USB contents and controlling scan jobs.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scanner", tags=["scanner"])

# Module-level references — set by init_scanner_api()
_scanner = None  # TrackScanner
_bridge_manager = None
_cache = None
_ws_manager = None


class StartScanRequest(BaseModel):
    player: int
    slot: str = "usb"
    mode: str = "all"  # "all" | "subset" | "single"
    track_ids: list[int] | None = None
    force_rescan: bool = False
    target_players: list[int] | None = None  # Multi-deck: which decks to use


def init_scanner_api(bridge_manager, cache, ws_manager) -> None:
    """Store references for scanner endpoints. Scanner is created on demand."""
    global _bridge_manager, _cache, _ws_manager
    _bridge_manager = bridge_manager
    _cache = cache
    _ws_manager = ws_manager


def _get_or_create_scanner():
    """Get the active scanner, creating one if needed."""
    global _scanner
    if _scanner is not None and _scanner.is_scanning:
        return _scanner

    if _bridge_manager is None:
        raise HTTPException(status_code=503, detail="Bridge manager not initialized")

    ws_client = _bridge_manager.ws_client
    if ws_client is None:
        raise HTTPException(status_code=503, detail="Bridge not connected")

    from ..layer1.scanner import TrackScanner

    async def _on_progress(progress):
        if _ws_manager:
            await _ws_manager.broadcast({
                "type": "scan_progress",
                "payload": progress.to_dict(),
            })

    async def _on_track_captured(captured):
        # Persist to SQLite
        if _cache:
            _cache.store_bridge_scan_data(
                source_player=captured.source_player,
                source_slot="usb",
                data={
                    "rekordbox_id": captured.rekordbox_id,
                    "title": captured.title,
                    "artist": captured.artist,
                    "album": captured.album,
                    "genre": captured.genre,
                    "key": captured.key,
                    "bpm": captured.bpm,
                    "duration": captured.duration,
                    "color": captured.color,
                    "rating": captured.rating,
                    "comment": captured.comment,
                    "beat_grid": captured.beat_grid,
                    "phrases": captured.phrases,
                    "cue_points": captured.cue_points,
                    "memory_points": captured.memory_points,
                    "hot_cues": captured.hot_cues,
                    "waveform_data": captured.waveform_data,
                    "waveform_frame_count": captured.waveform_frame_count,
                    "waveform_total_time_ms": captured.waveform_total_time_ms,
                    "waveform_is_color": captured.waveform_is_color,
                },
            )

    _scanner = TrackScanner(
        ws_client=ws_client,
        cache=_cache,
        on_progress=_on_progress,
        on_track_captured=_on_track_captured,
    )

    # Wire the adapter's Finder data callback to the scanner
    from ..bridge.messages import (
        BEAT_GRID,
        CUE_POINTS,
        PHRASE_ANALYSIS,
        TRACK_METADATA,
        TRACK_WAVEFORM,
    )

    _finder_dispatch = {
        TRACK_METADATA: _scanner.on_track_metadata,
        BEAT_GRID: _scanner.on_beat_grid,
        PHRASE_ANALYSIS: _scanner.on_phrase_analysis,
        CUE_POINTS: _scanner.on_cue_points,
        TRACK_WAVEFORM: _scanner.on_track_waveform,
    }

    def _on_finder_data(player_number: int, msg_type: str, payload: dict) -> None:
        handler = _finder_dispatch.get(msg_type)
        if handler:
            handler(player_number, payload)

    _bridge_manager.adapter.on_finder_data = _on_finder_data

    return _scanner


@router.get("/browse/{player}/{slot}")
async def browse_usb(player: int, slot: str = "usb"):
    """Browse all tracks on a player's USB/SD slot."""
    scanner = _get_or_create_scanner()
    try:
        tracks = await scanner.browse_all_tracks(player, slot)
        return {
            "player": player,
            "slot": slot,
            "track_count": len(tracks),
            "tracks": [
                {
                    "rekordbox_id": t.rekordbox_id,
                    "title": t.title,
                    "artist": t.artist,
                }
                for t in tracks
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _normalize_menu_item(raw: dict) -> dict:
    """Normalize a bridge menu item to {id, name, is_folder}.

    Root menu items: {item_type, text1, text2, id}
    Folder items:    {item_type, title, artist, rekordbox_id}
    """
    item_type = raw.get("item_type", "")
    # Root menu items use text1 with ￺/￻ delimiters, folder items use title
    name = raw.get("text1", "") or raw.get("title", "") or raw.get("name", "")
    # Strip Pioneer ￺/￻ delimiters from root menu names
    name = name.replace("\ufffa", "").replace("\ufffb", "")
    # Determine ID: root menu uses 'id', folder items use 'rekordbox_id'
    item_id = raw.get("id", 0) or raw.get("rekordbox_id", 0)
    # Folder-like types end with _menu or are playlist/folder types
    is_folder = item_type.endswith("_menu") or item_type in ("playlist", "folder")
    return {"id": item_id, "name": name, "is_folder": is_folder}


@router.get("/browse/{player}/{slot}/menu")
async def browse_root_menu(player: int, slot: str = "usb"):
    """Browse the root menu (folders/playlists) on a player's slot."""
    scanner = _get_or_create_scanner()
    try:
        resp = await scanner.browse_root_menu(player, slot)
        if not resp.ok:
            raise HTTPException(status_code=500, detail=resp.error_message)
        data = resp.data or {}
        items = [_normalize_menu_item(i) for i in data.get("items", [])]
        return {"items": items}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/browse/{player}/{slot}/folder/{folder_id}")
async def browse_folder(player: int, slot: str, folder_id: int):
    """Browse tracks/folders within a specific folder."""
    scanner = _get_or_create_scanner()
    try:
        resp = await scanner.browse_playlist(player, slot, folder_id)
        if not resp.ok:
            raise HTTPException(status_code=500, detail=resp.error_message)
        data = resp.data or {}
        # Separate folder items from track items
        raw_items = data.get("items", [])
        items = [_normalize_menu_item(i) for i in raw_items if _is_folder_item(i)]
        tracks = [
            {
                "rekordbox_id": i.get("rekordbox_id", 0),
                "title": i.get("title", ""),
                "artist": i.get("artist", ""),
            }
            for i in raw_items if not _is_folder_item(i)
        ]
        # Also include any tracks from a separate tracks key
        tracks.extend(data.get("tracks", []))
        return {"items": items, "tracks": tracks}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _is_folder_item(raw: dict) -> bool:
    """Check if a raw bridge item represents a folder/menu (vs a track)."""
    item_type = raw.get("item_type", "")
    return item_type.endswith("_menu") or item_type in ("playlist", "folder")


@router.post("/start")
async def start_scan(req: StartScanRequest):
    """Start a scan job."""
    scanner = _get_or_create_scanner()

    if scanner.is_scanning:
        raise HTTPException(status_code=409, detail="Scan already in progress")

    import asyncio

    # Start scan in background task
    async def _run_scan():
        try:
            await scanner.start_scan(
                player=req.player,
                slot=req.slot,
                track_ids=req.track_ids,
                force_rescan=req.force_rescan,
                target_players=req.target_players,
            )
        except Exception as e:
            logger.error("Scan failed: %s", e)

    asyncio.create_task(_run_scan())

    return {
        "status": "started",
        "player": req.player,
        "slot": req.slot,
        "target_players": req.target_players or [req.player],
    }


@router.get("/status")
async def scan_status():
    """Get current scan progress."""
    if _scanner is None:
        from ..layer1.scanner import ScanProgress
        return ScanProgress().to_dict()
    return _scanner.progress.to_dict()


@router.post("/stop")
async def stop_scan():
    """Stop the current scan after the current track."""
    if _scanner is None or not _scanner.is_scanning:
        raise HTTPException(status_code=409, detail="No scan in progress")

    _scanner.stop_scan()
    return {"status": "stopping"}


@router.get("/history")
async def scan_history():
    """List all tracks that have been scanned via bridge."""
    if _cache is None:
        return {"tracks": []}
    return {"tracks": _cache.list_bridge_scan_data()}
