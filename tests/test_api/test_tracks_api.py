"""Tests for tracks API endpoints — batch job lifecycle and scan deduplication.

Only tests cases where the API layer adds logic beyond simple passthrough:
- Batch analysis job state machine (pending → running → complete/failed)
- Directory scan deduplication (new vs already-analyzed fingerprint check)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import scue.api.jobs as jobs_module
from scue.api.tracks import router, init_tracks_api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_app(store: Any, cache: Any) -> FastAPI:
    """Create a minimal FastAPI app with the tracks router and injected mocks."""
    app = FastAPI()
    app.include_router(router)
    # Inject mocks directly into the module globals
    import scue.api.tracks as tracks_mod
    tracks_mod._store = store
    tracks_mod._cache = cache
    tracks_mod._tracks_dir = Path("/fake/tracks")
    tracks_mod._cache_path = Path("/fake/cache.db")
    return app


def _clear_jobs() -> None:
    """Clear the in-memory job registry between tests."""
    jobs_module._jobs.clear()


def _make_mock_store(existing_fps: set[str] | None = None) -> MagicMock:
    """Create a mock TrackStore.

    Args:
        existing_fps: Set of fingerprints that store.exists() should return True for.
    """
    store = MagicMock()
    fps = existing_fps or set()
    store.exists.side_effect = lambda fp: fp in fps
    return store


def _make_mock_cache() -> MagicMock:
    """Create a minimal mock TrackCache."""
    cache = MagicMock()
    cache.list_tracks.return_value = []
    cache.count_tracks.return_value = 0
    return cache


# ---------------------------------------------------------------------------
# Batch Job Lifecycle
# ---------------------------------------------------------------------------


class TestBatchJobLifecycle:
    """Tests for POST /api/tracks/analyze-batch and GET /api/tracks/jobs/{job_id}."""

    def setup_method(self) -> None:
        _clear_jobs()

    def test_post_batch_creates_job_returns_job_id(self, tmp_path: Path) -> None:
        """POST with valid paths creates a job and returns a job_id."""
        store = _make_mock_store()
        cache = _make_mock_cache()
        app = _build_app(store, cache)
        client = TestClient(app)

        # Create real temp files so Path.exists() passes
        f1 = tmp_path / "track1.mp3"
        f2 = tmp_path / "track2.mp3"
        f1.write_bytes(b"fake audio")
        f2.write_bytes(b"fake audio")

        # run_analysis is imported inside _run_batch_analysis at call time, so patch at source.
        # asyncio.to_thread is patched so background tasks run synchronously in TestClient.
        with (
            patch("scue.layer1.analysis.run_analysis", return_value=None),
            patch("scue.api.tracks.asyncio.to_thread", new=_fake_to_thread),
            patch("scue.layer1.fingerprint.compute_fingerprint", return_value="aabbcc"),
        ):
            resp = client.post(
                "/api/tracks/analyze-batch",
                json={"paths": [str(f1), str(f2)]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert isinstance(data["job_id"], str)
        assert len(data["job_id"]) > 0

    def test_get_job_returns_correct_state_progression(self, tmp_path: Path) -> None:
        """GET /api/tracks/jobs/{job_id} reflects state after background task runs."""
        store = _make_mock_store()
        cache = _make_mock_cache()
        app = _build_app(store, cache)
        client = TestClient(app)

        f1 = tmp_path / "track.mp3"
        f1.write_bytes(b"fake audio")

        with (
            patch("scue.layer1.analysis.run_analysis", return_value=None),
            patch("scue.api.tracks.asyncio.to_thread", new=_fake_to_thread),
            patch("scue.layer1.fingerprint.compute_fingerprint", return_value="deadbeef"),
        ):
            post_resp = client.post(
                "/api/tracks/analyze-batch",
                json={"paths": [str(f1)]},
            )
            job_id = post_resp.json()["job_id"]

            get_resp = client.get(f"/api/tracks/jobs/{job_id}")

        assert get_resp.status_code == 200
        job_data = get_resp.json()
        assert job_data["job_id"] == job_id
        # Background tasks run synchronously in TestClient — job is complete by poll time
        assert job_data["status"] == "complete"
        assert job_data["total"] == 1
        assert job_data["completed"] == 1
        assert job_data["failed"] == 0
        assert "results" in job_data
        assert len(job_data["results"]) == 1
        assert job_data["results"][0]["status"] == "done"

    def test_job_with_invalid_paths_rejected_before_create(self, tmp_path: Path) -> None:
        """POST with non-existent path returns 400 before any job is created."""
        store = _make_mock_store()
        cache = _make_mock_cache()
        app = _build_app(store, cache)
        client = TestClient(app)

        f1 = tmp_path / "real.mp3"
        f1.write_bytes(b"fake audio")
        missing = "/absolutely/does/not/exist/track.mp3"

        resp = client.post(
            "/api/tracks/analyze-batch",
            json={"paths": [str(f1), missing]},
        )

        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()
        # No job should have been created
        assert len(jobs_module._jobs) == 0

    def test_job_with_empty_paths_returns_400(self) -> None:
        """POST with empty paths list returns 400 immediately (no job created)."""
        store = _make_mock_store()
        cache = _make_mock_cache()
        app = _build_app(store, cache)
        client = TestClient(app)

        resp = client.post("/api/tracks/analyze-batch", json={"paths": []})

        assert resp.status_code == 400
        assert len(jobs_module._jobs) == 0

    def test_get_unknown_job_id_returns_404(self) -> None:
        """GET /api/tracks/jobs/{bad_id} returns 404 for unknown job IDs."""
        store = _make_mock_store()
        cache = _make_mock_cache()
        app = _build_app(store, cache)
        client = TestClient(app)

        resp = client.get("/api/tracks/jobs/nonexistent123")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Scan Deduplication
# ---------------------------------------------------------------------------


class TestScanDeduplication:
    """Tests for POST /api/tracks/scan deduplication logic."""

    def test_scan_mix_of_new_and_existing(self, tmp_path: Path) -> None:
        """Scan with a mix of new and already-analyzed files returns correct counts."""
        # Create 3 audio files
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f3 = tmp_path / "c.mp3"
        for f in (f1, f2, f3):
            f.write_bytes(b"fake audio")

        # f1 and f2 are "already analyzed" (their fps are in the store)
        fp_map = {
            str(f1): "fp_aaa",
            str(f2): "fp_bbb",
            str(f3): "fp_ccc",
        }
        known_fps = {"fp_aaa", "fp_bbb"}  # f3 is new

        store = _make_mock_store(existing_fps=known_fps)
        cache = _make_mock_cache()
        app = _build_app(store, cache)
        client = TestClient(app)

        def _fake_fp(path: Path) -> str:
            return fp_map[str(path)]

        with patch("scue.layer1.fingerprint.compute_fingerprint", side_effect=_fake_fp):
            resp = client.post("/api/tracks/scan", json={"path": str(tmp_path)})

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_files"] == 3
        assert data["already_analyzed"] == 2
        assert len(data["new_files"]) == 1
        assert data["new_files"][0]["filename"] == "c.mp3"

    def test_scan_nonexistent_path_returns_error(self) -> None:
        """Scan with a non-existent path returns 400."""
        store = _make_mock_store()
        cache = _make_mock_cache()
        app = _build_app(store, cache)
        client = TestClient(app)

        resp = client.post(
            "/api/tracks/scan", json={"path": "/absolutely/does/not/exist"}
        )

        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()

    def test_scan_empty_directory_returns_zero_files(self, tmp_path: Path) -> None:
        """Scan of an empty directory returns zero files with no errors."""
        store = _make_mock_store()
        cache = _make_mock_cache()
        app = _build_app(store, cache)
        client = TestClient(app)

        resp = client.post("/api/tracks/scan", json={"path": str(tmp_path)})

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_files"] == 0
        assert data["already_analyzed"] == 0
        assert data["new_files"] == []


# ---------------------------------------------------------------------------
# Helpers — asyncio.to_thread substitute for sync test context
# ---------------------------------------------------------------------------


async def _fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Synchronous substitute for asyncio.to_thread used inside background tasks.

    TestClient runs background tasks synchronously via a new event loop call.
    asyncio.to_thread may not behave as expected in that context, so we replace
    it with a direct call.
    """
    return func(*args, **kwargs)
