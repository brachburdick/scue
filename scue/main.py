"""SCUE FastAPI server entry point.

Serves the browser UI, handles track upload/analysis, and bridges real-time
Pioneer DJ data to browser clients via WebSocket.

Run with:
    uvicorn scue.main:app --reload
"""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from scue.layer1.analysis import run_analysis
from scue.layer1.prodjlink import ProDJLinkClient
from scue.ui.websocket import ws_clients, broadcast, broadcast_json

# ── Directory paths ────────────────────────────────────────────────────────

_HERE = Path(__file__).parent               # scue/
PROJECT_ROOT = _HERE.parent                 # project root

UPLOAD_DIR = PROJECT_ROOT / "uploads"
STATIC_DIR = _HERE / "ui" / "static"

ALLOWED_EXTENSIONS = {".wav", ".mp3"}
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB

UPLOAD_DIR.mkdir(exist_ok=True)

# ── Pioneer real-time state ────────────────────────────────────────────────

pioneer = ProDJLinkClient()


def _on_deck_update(channel: int, state: dict):
    """Called by ProDJLinkClient on every status packet."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(broadcast_json({"type": "deck_update", "channel": channel, "data": state}))
            loop.create_task(_broadcast_pioneer_status())
    except RuntimeError:
        pass


async def _broadcast_pioneer_status():
    await broadcast_json({
        "type": "pioneer_status",
        "is_receiving": pioneer.is_receiving,
        "active_channels": pioneer.active_channels,
        "packet_count": pioneer.packet_count,
    })


pioneer.on_update(_on_deck_update)


async def _pioneer_watchdog():
    """Push pioneer_status every 2s so the UI reflects when devices go stale."""
    while True:
        await asyncio.sleep(2)
        if ws_clients:
            await _broadcast_pioneer_status()


# ── App lifecycle ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await pioneer.start()
    watchdog = asyncio.create_task(_pioneer_watchdog())
    yield
    watchdog.cancel()
    pioneer.stop()


app = FastAPI(
    title="SCUE",
    description="EDM Music Structure Analyzer & Automated DJ Cue System",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── WebSocket ──────────────────────────────────────────────────────────────

@app.websocket("/ws/pioneer")
async def pioneer_ws(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    # Immediately send current state + connection status
    await ws.send_text(json.dumps({"type": "full_state", "decks": pioneer.get_state()}))
    await ws.send_text(json.dumps({
        "type": "pioneer_status",
        "is_receiving": pioneer.is_receiving,
        "active_channels": pioneer.active_channels,
        "packet_count": pioneer.packet_count,
    }))
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
            elif data == "get_state":
                await ws.send_text(json.dumps({"type": "full_state", "decks": pioneer.get_state()}))
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(ws)


# ── Diagnostics ────────────────────────────────────────────────────────────

@app.get("/api/pioneer/debug")
async def pioneer_debug():
    """Returns raw diagnostics: bound sockets, packet count, recent packets."""
    return pioneer.get_debug_info()


# ── Upload / Analysis ──────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/api/upload")
async def upload(file: UploadFile):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext!r} not supported. Use .wav or .mp3")

    track_id = str(uuid.uuid4())
    filepath = UPLOAD_DIR / f"{track_id}{ext}"

    size = 0
    with open(filepath, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                filepath.unlink(missing_ok=True)
                raise HTTPException(413, "File too large (max 200 MB)")
            f.write(chunk)

    return {"track_id": track_id, "filename": file.filename, "ext": ext}


@app.post("/api/analyze/{track_id}")
async def analyze(track_id: str, penalty: float = 5.0):
    filepath = _find_track(track_id)
    if not filepath:
        raise HTTPException(404, "Track not found")
    try:
        result = run_analysis(str(filepath), ruptures_penalty=penalty)
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")
    result["track_id"] = track_id
    return result


@app.get("/api/audio/{track_id}")
async def get_audio(track_id: str):
    filepath = _find_track(track_id)
    if not filepath:
        raise HTTPException(404, "Track not found")
    ext = filepath.suffix.lower()
    return FileResponse(str(filepath), media_type="audio/wav" if ext == ".wav" else "audio/mpeg")


def _find_track(track_id: str) -> Path | None:
    for ext in ALLOWED_EXTENSIONS:
        path = UPLOAD_DIR / f"{track_id}{ext}"
        if path.exists():
            return path
    return None
