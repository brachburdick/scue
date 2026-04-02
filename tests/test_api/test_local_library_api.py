"""Tests for local library API endpoints and WebSocket progress delivery."""

from __future__ import annotations

import json
import queue
import sys
import threading
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import scue.api.local_library as local_library_module
from scue.api.local_library import init_local_library_api, router as local_library_router
from scue.api.ws import init_ws, router as ws_router
from scue.api.ws_manager import WSManager


def _build_app(store: MagicMock) -> FastAPI:
    """Create a minimal app with the local-library + WS routers wired up."""
    app = FastAPI()
    app.include_router(local_library_router)
    app.include_router(ws_router)

    ws_manager = WSManager()
    bridge_manager = MagicMock()
    bridge_manager.to_status_dict.return_value = {
        "status": "idle",
        "devices": {},
        "players": {},
    }
    bridge_manager._adapter = SimpleNamespace(devices={}, players={})

    init_local_library_api(store, MagicMock(), ws_manager=ws_manager)
    init_ws(ws_manager, bridge_manager)
    return app


def _make_fake_content(audio_path: Path, idx: int) -> SimpleNamespace:
    """Create a fake rekordbox content row with just the fields scan_master_db uses."""
    return SimpleNamespace(
        ID=idx,
        Title=f"Track {idx}",
        Artist=None,
        BPM=12800,
        Key=None,
        Genre=None,
        Rating=0,
        Length=180000,
        FolderPath=str(audio_path),
        AnalysisDataPath="",
    )


class _FakeRekordbox6Database:
    """Minimal fake for pyrekordbox.Rekordbox6Database."""

    def __init__(self, _db_path: Path, contents: list[SimpleNamespace]) -> None:
        self._contents = contents

    def get_content(self) -> list[SimpleNamespace]:
        return self._contents


def test_master_db_scan_streams_progress_during_fingerprinting(tmp_path: Path) -> None:
    """A WS client receives scan progress before the POST returns.

    Regression for GIL starvation in the fingerprint batch: progress callbacks are
    scheduled from the executor thread, so we need explicit GIL yields for the
    event loop to process them before the scan completes.
    """
    tracks_dir = tmp_path / "audio"
    tracks_dir.mkdir()
    audio_files = []
    for idx in range(60):
        path = tracks_dir / f"track-{idx}.mp3"
        path.write_bytes(b"x")
        audio_files.append(path)

    contents = [_make_fake_content(path, idx) for idx, path in enumerate(audio_files, start=1)]
    master_db_path = tmp_path / "master.db"
    master_db_path.write_bytes(b"")

    fake_pyrekordbox = ModuleType("pyrekordbox")
    fake_pyrekordbox.Rekordbox6Database = (
        lambda db_path: _FakeRekordbox6Database(db_path, contents)
    )

    store = MagicMock()
    store.exists.return_value = False
    app = _build_app(store)

    original_switch_interval = sys.getswitchinterval()
    post_done = threading.Event()
    received_messages: queue.Queue[dict] = queue.Queue()
    receiver_errors: queue.Queue[BaseException] = queue.Queue()
    post_result: dict = {}

    def _cpu_bound_fingerprint(path: Path) -> str:
        total = 0
        for i in range(80_000):
            total += i
        return f"{path.stem}-{total}"

    def _post_scan(client: TestClient) -> None:
        try:
            response = client.post("/api/local-library/master-db/scan")
            post_result["status_code"] = response.status_code
            post_result["json"] = response.json()
        finally:
            post_done.set()

    try:
        with (
            patch.dict(sys.modules, {"pyrekordbox": fake_pyrekordbox}),
            patch("scue.layer1.masterdb_scanner.detect_master_db", return_value=master_db_path),
            patch("scue.layer1.masterdb_scanner.create_sidecars_from_master_db", return_value=0),
            patch("scue.layer1.masterdb_scanner._compute_fingerprint", side_effect=_cpu_bound_fingerprint),
            TestClient(app) as client,
        ):
            local_library_module._last_masterdb_scan = None
            local_library_module._scan_in_progress = False
            sys.setswitchinterval(60.0)

            with client.websocket_connect("/ws") as ws:
                # Initial bridge_status on connect.
                initial = json.loads(ws.receive_text())
                assert initial["type"] == "bridge_status"

                def _receiver() -> None:
                    try:
                        while True:
                            message = json.loads(ws.receive_text())
                            received_messages.put(message)
                            if (
                                message.get("type") == "rekordbox_progress"
                                and message.get("payload", {}).get("phase") in {"scan_complete", "error"}
                            ):
                                return
                    except BaseException as exc:  # pragma: no cover - defensive cleanup path
                        receiver_errors.put(exc)

                receiver_thread = threading.Thread(target=_receiver, daemon=True)
                receiver_thread.start()

                post_thread = threading.Thread(target=_post_scan, args=(client,), daemon=True)
                post_thread.start()

                progress_arrived_while_scan_running = False
                saw_terminal_progress = False
                deadline = time.monotonic() + 10.0

                while time.monotonic() < deadline:
                    try:
                        message = received_messages.get(timeout=0.1)
                    except queue.Empty:
                        if post_done.is_set():
                            break
                        continue

                    if message.get("type") != "rekordbox_progress":
                        continue

                    payload = message["payload"]
                    if (
                        payload.get("message") == "Computing fingerprints"
                        and payload.get("detail", {}).get("current", 0) >= 20
                        and not post_done.is_set()
                    ):
                        progress_arrived_while_scan_running = True

                    if payload.get("phase") in {"scan_complete", "error"}:
                        saw_terminal_progress = True
                        break

                post_thread.join(timeout=10.0)
                receiver_thread.join(timeout=10.0)
    finally:
        sys.setswitchinterval(original_switch_interval)

    if not receiver_errors.empty():
        raise receiver_errors.get()

    assert post_done.is_set()
    assert post_result["status_code"] == 200
    assert post_result["json"] == {"status": "started"}
    assert progress_arrived_while_scan_running
    assert saw_terminal_progress
