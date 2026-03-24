"""Tests for ground truth API endpoints — CRUD, scoring, and audio streaming."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scue.api.ground_truth import router as gt_router, init_ground_truth_api
from scue.api.audio import router as audio_router, init_audio_api


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_dirs(tmp_path: Path):
    """Create temporary ground_truth and tracks directories."""
    gt_dir = tmp_path / "ground_truth"
    gt_dir.mkdir()
    tracks_dir = tmp_path / "tracks"
    tracks_dir.mkdir()
    return gt_dir, tracks_dir


@pytest.fixture()
def client(tmp_dirs):
    """Create a test client with ground truth and audio routers."""
    gt_dir, tracks_dir = tmp_dirs
    app = FastAPI()
    app.include_router(gt_router)
    app.include_router(audio_router)
    init_ground_truth_api(gt_dir, tracks_dir)
    init_audio_api(tracks_dir)
    return TestClient(app)


FAKE_FP = "abc123def456"
SAMPLE_EVENTS = [
    {"type": "kick", "timestamp": 1.0},
    {"type": "kick", "timestamp": 2.0},
    {"type": "snare", "timestamp": 1.5},
    {"type": "riser", "timestamp": 10.0, "duration": 4.0},
]


# ---------------------------------------------------------------------------
# CRUD Tests
# ---------------------------------------------------------------------------


class TestGroundTruthCRUD:
    def test_list_empty(self, client: TestClient) -> None:
        resp = client.get("/api/ground-truth")
        assert resp.status_code == 200
        assert resp.json()["tracks"] == []

    def test_save_and_load(self, client: TestClient) -> None:
        # Save
        resp = client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": SAMPLE_EVENTS},
        )
        assert resp.status_code == 200
        assert resp.json()["event_count"] == 4

        # Load
        resp = client.get(f"/api/ground-truth/{FAKE_FP}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fingerprint"] == FAKE_FP
        assert len(data["events"]) == 4
        # Events should be sorted by timestamp
        timestamps = [e["timestamp"] for e in data["events"]]
        assert timestamps == sorted(timestamps)

    def test_load_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/ground-truth/nonexistent")
        assert resp.status_code == 404

    def test_save_overwrites(self, client: TestClient) -> None:
        # Save first version
        client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": SAMPLE_EVENTS},
        )
        # Save second version (fewer events)
        new_events = [{"type": "kick", "timestamp": 5.0}]
        resp = client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": new_events},
        )
        assert resp.json()["event_count"] == 1

        # Verify overwrite
        resp = client.get(f"/api/ground-truth/{FAKE_FP}")
        assert len(resp.json()["events"]) == 1

    def test_delete(self, client: TestClient) -> None:
        # Save then delete
        client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": SAMPLE_EVENTS},
        )
        resp = client.delete(f"/api/ground-truth/{FAKE_FP}")
        assert resp.status_code == 200

        # Verify deleted
        resp = client.get(f"/api/ground-truth/{FAKE_FP}")
        assert resp.status_code == 404

    def test_delete_not_found(self, client: TestClient) -> None:
        resp = client.delete("/api/ground-truth/nonexistent")
        assert resp.status_code == 404

    def test_list_after_save(self, client: TestClient) -> None:
        client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": SAMPLE_EVENTS},
        )
        resp = client.get("/api/ground-truth")
        tracks = resp.json()["tracks"]
        assert len(tracks) == 1
        assert tracks[0]["fingerprint"] == FAKE_FP
        assert tracks[0]["event_count"] == 4

    def test_save_validates_type_field(self, client: TestClient) -> None:
        resp = client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": [{"timestamp": 1.0}]},
        )
        assert resp.status_code == 400
        assert "type" in resp.json()["detail"]

    def test_save_validates_timestamp_field(self, client: TestClient) -> None:
        resp = client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": [{"type": "kick"}]},
        )
        assert resp.status_code == 400
        assert "timestamp" in resp.json()["detail"]

    def test_file_format_matches_eval_harness(self, client: TestClient, tmp_dirs) -> None:
        """Ground truth files must match the format expected by eval_detectors.py."""
        gt_dir, _ = tmp_dirs
        client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": SAMPLE_EVENTS},
        )
        # Read the raw file and verify it matches eval harness format
        raw = json.loads((gt_dir / f"{FAKE_FP}.json").read_text())
        assert isinstance(raw, list)
        for event in raw:
            assert "type" in event
            assert "timestamp" in event

    def test_save_with_source_field(self, client: TestClient) -> None:
        """Events with optional source field are accepted and persisted."""
        events = [
            {"type": "kick", "timestamp": 1.0, "source": "predicted"},
            {"type": "snare", "timestamp": 2.0, "source": "manual"},
            {"type": "clap", "timestamp": 3.0, "source": "corrected"},
        ]
        resp = client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": events},
        )
        assert resp.status_code == 200

        # Verify source persisted on load
        loaded = client.get(f"/api/ground-truth/{FAKE_FP}").json()["events"]
        sources = [e.get("source") for e in loaded]
        assert sources == ["predicted", "manual", "corrected"]

    def test_save_without_source_backwards_compat(self, client: TestClient) -> None:
        """Events without source field still work (backwards compat)."""
        events = [{"type": "kick", "timestamp": 1.0}]
        resp = client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": events},
        )
        assert resp.status_code == 200

        loaded = client.get(f"/api/ground-truth/{FAKE_FP}").json()["events"]
        assert "source" not in loaded[0]

    def test_save_rejects_invalid_source(self, client: TestClient) -> None:
        """Events with invalid source value are rejected."""
        events = [{"type": "kick", "timestamp": 1.0, "source": "bogus"}]
        resp = client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": events},
        )
        assert resp.status_code == 400
        assert "source" in resp.json()["detail"]

    def test_predictions_snapshot_saved_on_first_save(
        self, client: TestClient, tmp_dirs,
    ) -> None:
        """First save creates a .predictions.json snapshot of detector output."""
        gt_dir, _ = tmp_dirs

        @dataclass
        class FakeEvent:
            type: str
            timestamp: float
            duration: float | None = None
            intensity: float = 0.8
            payload: dict = field(default_factory=dict)

        @dataclass
        class FakeAnalysis:
            events: list = field(default_factory=list)
            drum_patterns: list = field(default_factory=list)
            beats: list = field(default_factory=list)
            downbeats: list = field(default_factory=list)

        fake = FakeAnalysis(events=[FakeEvent(type="kick", timestamp=1.0)])

        with patch("scue.layer1.storage.TrackStore") as MockStore:
            MockStore.return_value.load_latest.return_value = fake
            resp = client.put(
                f"/api/ground-truth/{FAKE_FP}",
                json={"events": [{"type": "kick", "timestamp": 1.0}]},
            )
            assert resp.status_code == 200

        pred_path = gt_dir / f"{FAKE_FP}.predictions.json"
        assert pred_path.exists()
        predictions = json.loads(pred_path.read_text())
        assert len(predictions) == 1
        assert predictions[0]["type"] == "kick"

    def test_predictions_snapshot_not_overwritten(
        self, client: TestClient, tmp_dirs,
    ) -> None:
        """Subsequent saves don't overwrite the predictions snapshot."""
        gt_dir, _ = tmp_dirs

        # Write a pre-existing predictions file
        pred_path = gt_dir / f"{FAKE_FP}.predictions.json"
        pred_path.write_text('[{"type": "original", "timestamp": 0.0}]')

        # Save ground truth (predictions snapshot should NOT be touched)
        client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": [{"type": "kick", "timestamp": 1.0}]},
        )

        # Verify original predictions file untouched
        predictions = json.loads(pred_path.read_text())
        assert predictions[0]["type"] == "original"


# ---------------------------------------------------------------------------
# Scoring Tests
# ---------------------------------------------------------------------------


class TestGroundTruthScoring:
    def test_score_no_ground_truth(self, client: TestClient) -> None:
        resp = client.post(f"/api/ground-truth/{FAKE_FP}/score")
        assert resp.status_code == 404

    def test_score_no_track(self, client: TestClient, tmp_dirs) -> None:
        # Save ground truth but no track analysis exists
        client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": SAMPLE_EVENTS},
        )
        resp = client.post(f"/api/ground-truth/{FAKE_FP}/score")
        assert resp.status_code == 404

    def test_score_with_matching_events(self, client: TestClient, tmp_dirs) -> None:
        """Score with a mock track that has matching events."""
        gt_dir, tracks_dir = tmp_dirs

        # Save ground truth
        client.put(
            f"/api/ground-truth/{FAKE_FP}",
            json={"events": [
                {"type": "kick", "timestamp": 1.0},
                {"type": "kick", "timestamp": 2.0},
            ]},
        )

        # Create a fake track analysis with matching events
        @dataclass
        class FakeEvent:
            type: str
            timestamp: float
            duration: float | None = None
            intensity: float = 0.8
            payload: dict = field(default_factory=dict)

        @dataclass
        class FakeAnalysis:
            events: list = field(default_factory=list)
            drum_patterns: list = field(default_factory=list)
            beats: list = field(default_factory=list)
            downbeats: list = field(default_factory=list)

        fake = FakeAnalysis(
            events=[
                FakeEvent(type="kick", timestamp=1.01),
                FakeEvent(type="kick", timestamp=2.02),
            ],
        )

        with patch("scue.layer1.storage.TrackStore") as MockStore:
            MockStore.return_value.load_latest.return_value = fake
            resp = client.post(f"/api/ground-truth/{FAKE_FP}/score")

        assert resp.status_code == 200
        data = resp.json()
        assert "kick" in data["scores"]
        kick = data["scores"]["kick"]
        assert kick["true_positives"] == 2
        assert kick["false_positives"] == 0
        assert kick["false_negatives"] == 0
        assert kick["precision"] == 1.0
        assert kick["recall"] == 1.0


# ---------------------------------------------------------------------------
# Audio Streaming Tests
# ---------------------------------------------------------------------------


class TestAudioStreaming:
    def test_stream_track_not_found(self, client: TestClient) -> None:
        resp = client.get(f"/api/audio/{FAKE_FP}")
        assert resp.status_code == 404

    def test_stream_audio_file_missing(self, client: TestClient, tmp_dirs) -> None:
        """Track exists but audio file was moved/deleted."""
        _, tracks_dir = tmp_dirs

        @dataclass
        class FakeAnalysis:
            audio_path: str = "/nonexistent/track.mp3"

        with patch("scue.api.audio.TrackStore") as MockStore:
            MockStore.return_value.load_latest.return_value = FakeAnalysis()
            resp = client.get(f"/api/audio/{FAKE_FP}")

        assert resp.status_code == 404
        assert "moved" in resp.json()["detail"]

    def test_stream_audio_success(self, client: TestClient, tmp_dirs) -> None:
        """Successfully stream an audio file."""
        _, tracks_dir = tmp_dirs

        # Create a fake audio file
        audio_file = tmp_dirs[0].parent / "test.mp3"
        audio_file.write_bytes(b"fake mp3 data")

        @dataclass
        class FakeAnalysis:
            audio_path: str = str(audio_file)

        with patch("scue.api.audio.TrackStore") as MockStore:
            MockStore.return_value.load_latest.return_value = FakeAnalysis()
            resp = client.get(f"/api/audio/{FAKE_FP}")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/mpeg"
