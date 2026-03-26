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

### demucs.api.Separator not available in demucs 4.0.1
Date: 2026-03-24
Milestone: Strata Phase 5
**Symptom:** Standard tier analysis fails at stem separation step with `No module named 'demucs.api'`.
**Root Cause:** `separation.py` used `demucs.api.Separator` which was introduced in a later version of demucs. Installed version is 4.0.1 which doesn't have the `api` submodule.
**Fix:** Replaced with compatible API: `demucs.pretrained.get_model()` + `demucs.apply.apply_model()` + `demucs.audio.AudioFile`. These are available in demucs 4.0.x.
**Files:** `scue/layer1/strata/separation.py`

### PPTH parser reads len_path at wrong offset — local library scan returns 0 tracks
Date: 2026-03-25
Milestone: Bridge Command Channel
**Symptom:** Local rekordbox library scan (`POST /api/local-library/scan`) returns `total_tracks: 0` despite detecting 6090 DAT files. All files fail PPTH parsing.
**Root Cause:** `parse_anlz_file_path()` in `anlz_parser.py` read `len_path` at offset `header_len` (typically 16) instead of the correct offset 12. At offset 16, it was reading the first bytes of the path string as a u32, producing a huge bogus length (e.g. 4128835) that exceeded the section size.
**Fix:** Changed `len_path` read from `struct.unpack_from(">I", section_data, header_len)` to `struct.unpack_from(">I", section_data, 12)`. Path bytes start at offset 16 (12 + 4). PPTH layout: tag(4) + header_len(4) + total_len(4) + len_path(4) + path_bytes.
**Note:** Unit tests passed with the old code because the synthetic test data used `header_len=16`, which happened to coincide with offset 12+4. Real rekordbox files exposed the bug.
**Files:** `scue/layer1/anlz_parser.py`
