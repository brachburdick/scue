"""REST API endpoints for ground truth annotation management.

Provides CRUD operations for ground truth event labels:
- GET /api/ground-truth — list tracks with ground truth
- GET /api/ground-truth/{fingerprint} — load annotations
- PUT /api/ground-truth/{fingerprint} — save/overwrite annotations
- DELETE /api/ground-truth/{fingerprint} — delete annotations
- POST /api/ground-truth/{fingerprint}/score — run eval harness
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ground-truth", tags=["ground-truth"])

_gt_dir: Path | None = None
_tracks_dir: Path | None = None


def init_ground_truth_api(ground_truth_dir: Path, tracks_dir: Path) -> None:
    """Initialize the ground truth API with storage paths.

    Called during app startup.
    """
    global _gt_dir, _tracks_dir
    _gt_dir = ground_truth_dir
    _tracks_dir = tracks_dir
    _gt_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Ground truth API initialized: %s", _gt_dir)


def _get_gt_dir() -> Path:
    if _gt_dir is None:
        raise HTTPException(500, "Ground truth store not initialized")
    return _gt_dir


def _get_tracks_dir() -> Path:
    if _tracks_dir is None:
        raise HTTPException(500, "Tracks store not initialized")
    return _tracks_dir


def _gt_path(fingerprint: str) -> Path:
    return _get_gt_dir() / f"{fingerprint}.json"


@router.get("")
async def list_ground_truth() -> dict:
    """List all fingerprints that have ground truth annotations."""
    gt_dir = _get_gt_dir()
    tracks = []
    for f in sorted(gt_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            tracks.append({
                "fingerprint": f.stem,
                "event_count": len(data),
                "updated_at": f.stat().st_mtime,
            })
        except (json.JSONDecodeError, OSError):
            logger.warning("Skipping invalid ground truth file: %s", f)
    return {"tracks": tracks}


@router.get("/{fingerprint}")
async def get_ground_truth(fingerprint: str) -> dict:
    """Load ground truth annotations for a track."""
    path = _gt_path(fingerprint)
    if not path.exists():
        raise HTTPException(404, f"No ground truth for track: {fingerprint[:16]}")
    try:
        events = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Invalid ground truth JSON: {e}")
    return {
        "fingerprint": fingerprint,
        "events": events,
        "updated_at": path.stat().st_mtime,
    }


class SaveGroundTruthRequest(BaseModel):
    events: list[dict]


def _save_predictions_snapshot(fingerprint: str, dest: Path) -> None:
    """Snapshot current detector output as the frozen prediction baseline.

    Written once on first ground-truth save. Never overwritten on subsequent saves.
    """
    try:
        from ..layer1.detectors.events import expand_patterns
        from ..layer1.models import event_to_dict
        from ..layer1.storage import TrackStore

        store = TrackStore(_get_tracks_dir())
        analysis = store.load_latest(fingerprint)
        if analysis is None:
            logger.info("No track analysis for %s — skipping predictions snapshot", fingerprint[:16])
            return

        detected = [event_to_dict(e) for e in analysis.events]
        if analysis.drum_patterns:
            expanded = expand_patterns(
                analysis.drum_patterns, analysis.beats, analysis.downbeats,
            )
            detected.extend([event_to_dict(e) for e in expanded])

        detected.sort(key=lambda e: e["timestamp"])
        dest.write_text(json.dumps(detected, indent=2) + "\n")
        logger.info(
            "Saved predictions snapshot for %s: %d events", fingerprint[:16], len(detected),
        )
    except Exception:
        logger.warning("Failed to save predictions snapshot for %s", fingerprint[:16], exc_info=True)


_VALID_SOURCES = {"predicted", "corrected", "manual"}


@router.put("/{fingerprint}")
async def save_ground_truth(fingerprint: str, req: SaveGroundTruthRequest) -> dict:
    """Save or overwrite ground truth annotations for a track.

    Events format: [{"type": "kick", "timestamp": 1.234, "source": "manual"}, ...]
    The optional ``source`` field tracks annotation origin (predicted/corrected/manual).
    """
    # Validate event structure
    for i, event in enumerate(req.events):
        if "type" not in event:
            raise HTTPException(400, f"Event {i} missing 'type' field")
        if "timestamp" not in event:
            raise HTTPException(400, f"Event {i} missing 'timestamp' field")
        if "source" in event and event["source"] not in _VALID_SOURCES:
            raise HTTPException(
                400,
                f"Event {i} has invalid 'source': {event['source']!r} "
                f"(expected one of {sorted(_VALID_SOURCES)})",
            )

    path = _gt_path(fingerprint)

    # On first save, snapshot the current detector predictions alongside ground truth.
    # This frozen baseline enables correction-rate analysis later.
    predictions_path = _get_gt_dir() / f"{fingerprint}.predictions.json"
    if not predictions_path.exists():
        _save_predictions_snapshot(fingerprint, predictions_path)

    # Sort by timestamp for consistent output
    sorted_events = sorted(req.events, key=lambda e: e["timestamp"])
    path.write_text(json.dumps(sorted_events, indent=2) + "\n")
    logger.info(
        "Saved ground truth for %s: %d events", fingerprint[:16], len(sorted_events),
    )
    return {"ok": True, "event_count": len(sorted_events)}


@router.delete("/{fingerprint}")
async def delete_ground_truth(fingerprint: str) -> dict:
    """Delete ground truth annotations for a track."""
    path = _gt_path(fingerprint)
    if not path.exists():
        raise HTTPException(404, f"No ground truth for track: {fingerprint[:16]}")
    path.unlink()
    logger.info("Deleted ground truth for %s", fingerprint[:16])
    return {"ok": True}


@router.post("/{fingerprint}/score")
async def score_ground_truth(fingerprint: str) -> dict:
    """Run the eval harness: compare detected events against ground truth.

    Returns per-event-type precision, recall, and F1 scores.
    """
    from ..layer1.detectors.events import expand_patterns
    from ..layer1.eval_detectors import score_events
    from ..layer1.models import event_to_dict
    from ..layer1.storage import TrackStore

    # Load ground truth
    gt_path = _gt_path(fingerprint)
    if not gt_path.exists():
        raise HTTPException(404, f"No ground truth for track: {fingerprint[:16]}")
    ground_truth = json.loads(gt_path.read_text())

    # Load detected events from track analysis
    store = TrackStore(_get_tracks_dir())
    analysis = store.load_latest(fingerprint)
    if analysis is None:
        raise HTTPException(404, f"Track not found: {fingerprint[:16]}")

    detected = [event_to_dict(e) for e in analysis.events]

    # Expand drum patterns to individual events for scoring
    if analysis.drum_patterns:
        expanded = expand_patterns(
            analysis.drum_patterns,
            analysis.beats,
            analysis.downbeats,
        )
        detected.extend([event_to_dict(e) for e in expanded])

    # Score
    scores = score_events(detected, ground_truth)

    return {
        "fingerprint": fingerprint,
        "scores": {
            event_type: {
                "precision": sc.precision,
                "recall": sc.recall,
                "f1": sc.f1,
                "true_positives": sc.true_positives,
                "false_positives": sc.false_positives,
                "false_negatives": sc.false_negatives,
            }
            for event_type, sc in scores.items()
        },
        "total_detected": len(detected),
        "total_ground_truth": len(ground_truth),
    }
