# Bug Log — Layer 1 (Track Analysis & Live Tracking)

Append-only log of bugs found and fixed in the analysis pipeline (librosa, allin1-mlx, feature extraction, storage).
Record every fix, no matter how small — patterns emerge over time.

**Format:**
```
### Short title
Date: YYYY-MM-DD
Milestone: M-X (or N/A)
Symptom: What did the user see or what broke?
Root cause: Why did it happen?
Fix: What was changed and where?
File(s): path/to/file.py
```

---

### Beatgrid ms/seconds units mismatch between tracking and enrichment
Date: 2026-03-20
Milestone: M-1
Severity: HIGH (latent — will corrupt data once USB metadata is present)
Symptom: Not yet observed in production (no USB metadata flow yet). Will manifest as section snap calculations off by 1000x.
Root cause: `tracking.py:145` comment says "Extract beat timestamps in ms for enrichment" but `enrichment.py:65` documents `pioneer_beatgrid: beat timestamps from Pioneer (seconds)`. The code extracts `time_ms` values and passes them directly to enrichment which treats them as seconds. Classic multi-agent seam bug: both sides wrote reasonable code, but the contract between them was never tested end-to-end with real data.
Fix: Either divide by 1000 in tracking before passing to enrichment, or change enrichment to expect ms. Add a contract test that verifies units end-to-end with a real Pioneer-format beatgrid fixture.
File(s): scue/layer1/tracking.py (~line 145), scue/layer1/enrichment.py (~line 65)
Source: External code review 2026-03-20

### update_position() never wired in production
Date: 2026-03-20
Milestone: M-1
Severity: HIGH (latent — playback cursors always report position 0)
Symptom: `_player_position_ms` stays at 0.0 forever in production. Cursors always report position 0. Tests pass because they manually call `update_position()` before asserting.
Root cause: `update_position()` is defined on `PlaybackTracker` (tracking.py:100) and called in tests (test_tracking.py:86,109,126,176,192,203), but `main.py:105-108` only wires `on_player_update` and `on_track_loaded`. Nobody wires `adapter.on_beat` or any other callback to `_tracker.update_position()`. The adapter has an `on_beat` callback slot but nothing connects it to the tracker.
Fix: Wire `adapter.on_beat` (or extract position from `on_player_update`) to `_tracker.update_position()` in `main.py` startup.
File(s): scue/main.py (~line 105-108), scue/layer1/tracking.py (~line 100)
Source: External code review 2026-03-20

### rebuild_from_store() ignores enriched versions
Date: 2026-03-20
Milestone: M-1
Severity: MEDIUM
Symptom: Cache rebuild silently drops all enrichment work, reverting tracks to v1.
Root cause: `rebuild_from_store()` at storage.py:532 calls `store.load(fingerprint)` (no version arg = defaults to v1), not `store.load_latest(fingerprint)`. Additionally, `load_latest()` caps at version 10 — arbitrary ceiling.
Fix: Change `store.load(fingerprint)` to `store.load_latest(fingerprint)` in `rebuild_from_store()`.
File(s): scue/layer1/storage.py (~line 532)
Source: External code review 2026-03-20

### Background analysis blocks the event loop
Date: 2026-03-20
Milestone: M-1
Severity: HIGH
Symptom: During track analysis, WebSocket broadcasts, health checks, and all other async handlers stall. UI freezes or shows stale data.
Root cause: `_run_analysis_task()` at `scue/api/tracks.py:153` calls `run_analysis()` synchronously. FastAPI's `BackgroundTasks` runs the task on the same event loop. `run_analysis()` does CPU-heavy librosa/allin1 work, blocking all other async operations.
Fix: Wrap in `asyncio.to_thread(run_analysis, ...)` or use a `ProcessPoolExecutor`. One-line fix with big impact.
File(s): scue/api/tracks.py (~line 153)
Source: External code review 2026-03-20
