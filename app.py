"""FastAPI server for SCUE — EDM Music Structure Analyzer.

Serves the web UI, handles file upload/analysis, and bridges
real-time Pioneer DJ data (direct Pro DJ Link UDP) to browser
clients via WebSocket.
"""

import asyncio
import json
import os
import uuid

from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from analyzer.pipeline import run_analysis
from pioneer.prodj_link import ProDJLinkClient

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
ALLOWED_EXTENSIONS = {".wav", ".mp3"}
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── Pioneer real-time state ────────────────────────────────────────────────
pioneer = ProDJLinkClient()
ws_clients: set[WebSocket] = set()


def _on_deck_update(channel: int, state: dict):
    """Called by ProDJLinkClient on every status packet.
    Schedules a WebSocket broadcast from the sync OSC callback context.
    """
    deck_msg = json.dumps({"type": "deck_update", "channel": channel, "data": state})
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_broadcast(deck_msg))
            loop.create_task(_broadcast_pioneer_status())
    except RuntimeError:
        pass


async def _broadcast(msg: str):
    dead = set()
    for ws in ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    ws_clients -= dead


async def _broadcast_pioneer_status():
    msg = json.dumps({
        "type": "pioneer_status",
        "is_receiving": pioneer.is_receiving,
        "active_channels": pioneer.active_channels,
        "packet_count": pioneer.packet_count,
    })
    await _broadcast(msg)


pioneer.on_update(_on_deck_update)


async def _pioneer_watchdog():
    """Push status every 2 s so the UI reflects when devices go stale."""
    while True:
        await asyncio.sleep(2)
        if ws_clients:
            await _broadcast_pioneer_status()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await pioneer.start()
    watchdog = asyncio.create_task(_pioneer_watchdog())
    yield
    watchdog.cancel()
    pioneer.stop()


app = FastAPI(title="SCUE", description="EDM Music Structure Analyzer", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.post("/api/upload")
async def upload(file: UploadFile):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext!r} not supported. Use .wav or .mp3")

    track_id = str(uuid.uuid4())
    filepath = os.path.join(UPLOAD_DIR, f"{track_id}{ext}")

    size = 0
    with open(filepath, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                os.remove(filepath)
                raise HTTPException(413, "File too large (max 200 MB)")
            f.write(chunk)

    return {"track_id": track_id, "filename": file.filename, "ext": ext}


@app.post("/api/analyze/{track_id}")
async def analyze(track_id: str, penalty: float = 5.0):
    filepath = _find_track(track_id)
    if not filepath:
        raise HTTPException(404, "Track not found")
    try:
        result = run_analysis(filepath, ruptures_penalty=penalty)
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")
    result["track_id"] = track_id
    return result


@app.get("/api/audio/{track_id}")
async def get_audio(track_id: str):
    filepath = _find_track(track_id)
    if not filepath:
        raise HTTPException(404, "Track not found")
    ext = os.path.splitext(filepath)[1].lower()
    return FileResponse(filepath, media_type="audio/wav" if ext == ".wav" else "audio/mpeg")


def _find_track(track_id: str) -> str | None:
    for ext in ALLOWED_EXTENSIONS:
        path = os.path.join(UPLOAD_DIR, f"{track_id}{ext}")
        if os.path.exists(path):
            return path
    return None
