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
Severity: HIGH (mitigated)
Symptom: During track analysis, WebSocket broadcasts, health checks, and all other async handlers stall. UI freezes or shows stale data.
Root cause: `_run_analysis_task()` was originally async, running CPU-heavy librosa/allin1 work directly on the event loop.
Fix applied: `_run_analysis_task()` is now a sync function (not async def). FastAPI's `BackgroundTasks` runs sync functions in a thread pool via Starlette's `run_in_threadpool()`, keeping the event loop free. Librosa/numpy C extensions release the GIL during heavy computation, so event loop responsiveness is adequate.
Residual: True CPU-bound Python code between C calls still holds the GIL. A `ProcessPoolExecutor` would fully isolate analysis but adds pickling/IPC complexity — not warranted unless symptoms recur.
File(s): scue/api/tracks.py — `_run_analysis_task()`
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

### detectors.yaml path resolution off by one parent
Date: 2026-04-01
Milestone: N/A
**Symptom:** Every analysis logs "Detector config not found at .../scue/config/detectors.yaml, using defaults". Detectors work but always use hardcoded defaults instead of YAML config.
**Root Cause:** `load_detector_config()` in `events.py` used `Path(__file__).parent.parent.parent / "config"` which resolves to `scue/scue/config/` (inside the package). The actual config lives at `scue/config/` (project root). Needed one more `.parent`.
**Fix:** Changed to `Path(__file__).parent.parent.parent.parent / "config" / "detectors.yaml"` (4 levels up from `scue/layer1/detectors/events.py` to project root).
**Files:** `scue/layer1/detectors/events.py`

### "Metadata Only" import mode still queued full audio analysis
Date: 2026-04-01
Milestone: N/A
**Symptom:** Clicking Import with "Metadata Only" selected queued 2253 tracks for full audio analysis (fingerprinting, beat detection, sections, events). Import button hung for hours.
**Root Cause:** Frontend passed `skip_waveform: true` which only skipped the waveform rendering step — all other analysis still ran. No `metadata_only` flag existed.
**Fix:** Added `metadata_only: bool` to `MasterDbIngestRequest`. When true, Phase 2 (batch audio analysis) is skipped entirely. Frontend now sends `metadata_only: true` when import mode is "metadata".
**Files:** `scue/api/local_library.py`, `frontend/src/components/ingestion/RekordboxTab.tsx`, `frontend/src/types/ingestion.ts`

### Concurrent ingest processes from duplicate Import clicks
Date: 2026-04-01
Milestone: N/A
**Symptom:** Clicking Import multiple times spawned duplicate executor tasks that ran in parallel, causing overlapping fingerprint computations, CPU saturation, memory pressure, and eventual server unresponsiveness (WebSocket drops, frontend black screen).
**Root Cause:** No concurrency guard on the ingest endpoint. Each POST spawned a new `run_in_executor` task independently.
**Fix:** Added `_ingest_lock` (asyncio.Lock) as singleton guard — only one ingest runs at a time. New requests cancel in-progress ingests via `_ingest_cancel` (threading.Event) checked at loop heads in `ingest_from_master_db()`. Frontend disables Import button while active.
**Files:** `scue/api/local_library.py`, `scue/layer1/masterdb_scanner.py`, `frontend/src/components/ingestion/RekordboxTab.tsx`

### create_sidecars_from_master_db crashes on corrupt JSON analysis file
Date: 2026-04-01
Milestone: N/A
**Symptom:** "Scan Collection" returns 500 Internal Server Error after scanning 4510 tracks successfully. UI shows red "Scan failed: API 500" error.
**Root Cause:** `create_sidecars_from_master_db()` calls `store.load_latest(fingerprint)` for each matched track with no try/except. 10 of 891 matched tracks have corrupt JSON files (Extra data, Invalid control character, Expecting delimiter errors). One corrupt file kills the entire sidecar pass.
**Fix:** Wrapped `store.load_latest()` in try/except, logging a warning and skipping the corrupt track. Sidecar creation continues for remaining tracks.
**Files:** `scue/layer1/masterdb_scanner.py` (`create_sidecars_from_master_db()`)

### No memory cleanup between batch analysis files
Date: 2026-04-01
Milestone: N/A
**Symptom:** Server becomes unresponsive during large batch analysis (2000+ tracks). Memory grows unbounded.
**Root Cause:** librosa loads full audio into RAM per track. Python's GC is lazy and doesn't promptly free the ~35MB per track between iterations.
**Fix:** Added `gc.collect()` after each successful file in `_run_batch_analysis()`.
**Files:** `scue/api/tracks.py`

### [NOT REPRODUCED] Strata GET endpoint returns empty for existing analysis files
Date: 2026-04-02
Milestone: N/A
**Reported Symptom:** GET /api/tracks/{fp}/strata/quick returns pipeline_tier=None, sections=0 even though strata/{fp}.quick.analysis.json exists on disk with 22 sections.
**Reported Root Cause:** File lookup pattern mismatch between GET endpoint and analysis writer.
**Investigation:** Could not reproduce. Both the writer (`StrataEngine.analyze_quick` → `StrataStore.save`) and reader (`get_strata_tier` / `get_all_strata` → `StrataStore.load`) use the same `_path()` method generating `{fp}.{tier}.{source}.json`. Tested all 6 quick analysis files via `StrataStore.load()` and via FastAPI TestClient — all returned correct pipeline_tier and section counts. Legacy fallback (`{fp}.{tier}.json`) also works for the 2 legacy-only files.
**Side finding:** `_VALID_TIERS` in `scue/api/tracks.py:61` was missing `"hybrid"`, so `_scan_strata()` skipped hybrid strata files in the track list. Fixed. Not related to the reported symptom.
**Files:** `scue/api/strata.py`, `scue/layer1/strata/storage.py`, `scue/api/tracks.py`

### Non-atomic JSON writes corrupt analysis files on crash
Date: 2026-04-02
Milestone: N/A
**Symptom:** After a uvicorn worker crash (during large batch analysis), multiple track JSON files are left corrupt (`JSONDecodeError: Extra data`). On restart, `resume_incomplete_jobs` hits these files and logs batch failures. Corrupt files persist across restarts.
**Root Cause:** `TrackStore.save()`, `save_live_data()`, and `StrataStore.save()` all used direct `open("w")` + `json.dump()` writes. If the process is killed mid-write, the file is left in a partial/corrupt state (old content + partial new content = "Extra data").
**Fix:** All three writers now use atomic write pattern: write to a temp file (`tempfile.mkstemp` in the same directory), then `os.replace()` to atomically swap it into place. On any failure the temp file is cleaned up. Also made `TrackStore.load()` resilient to corrupt files — catches `JSONDecodeError`/`KeyError` and returns `None` with a warning log instead of propagating the exception.
**Files:** `scue/layer1/storage.py`, `scue/layer1/strata/storage.py`

### _VALID_TIERS missing "hybrid" — track listing skips hybrid strata files
Date: 2026-04-02
Milestone: N/A
**Symptom:** Tracks with hybrid strata data don't show "hybrid" in their available tiers on the track list endpoint.
**Root Cause:** `_VALID_TIERS` in `scue/api/tracks.py` was `{"quick", "standard", "deep", "live", "live_offline"}` — missing `"hybrid"`. The `_scan_strata()` function uses this set to filter filenames, so `{fp}.hybrid.pioneer_live.json` files were silently skipped.
**Fix:** Added `"hybrid"` to `_VALID_TIERS`.
**Files:** `scue/api/tracks.py`

### resume_incomplete_jobs kills server on every restart
Date: 2026-04-02
Milestone: N/A
**Symptom:** Backend worker process dies within minutes of every startup. uvicorn reload watcher parent holds port 8000 but no worker serves requests — frontend shows "Connecting…" indefinitely. Health endpoint times out. Happened repeatedly: the original session crash, every hot-reload from code edits, and every manual restart.
**Root Cause:** `resume_incomplete_jobs()` in `tracks.py` ran on every startup (including `--reload` restarts) and blindly spawned `asyncio.create_task(_run_batch_analysis(...))` for ALL incomplete jobs (2253 + 2383 tracks). Each task ran full librosa audio analysis in `asyncio.to_thread`, consuming ~35MB per track. With 4000+ tracks queued instantly, the worker OOM'd and was killed by the OS. The reload watcher parent survived (holding the socket), creating a zombie server.
**Fix:** `resume_incomplete_jobs()` no longer auto-resumes batch jobs. Instead it marks stale jobs with `status="stale"` (which `get_incomplete_jobs` won't re-select, since it only queries `pending`/`running`). Logged as informational. Users re-trigger analysis explicitly when ready.
**Files:** `scue/api/tracks.py`

### Ingest re-scans entire master.db instead of reusing scan results
Date: 2026-04-02
Milestone: N/A
**Symptom:** Clicking "Import" after "Scan Collection" shows "Parsing ANLZ data" and "Computing fingerprints" progress bars again for all ~4500 tracks (~2 minutes), even though the scan just computed this exact data. The import processes all tracks, not just the ~1697 remaining.
**Root Cause:** `_run_ingest_background()` called `ingest_from_master_db()` which re-reads master.db from scratch, re-opens pyrekordbox, re-parses all ANLZ files, and re-fingerprints every audio file — completely ignoring the `MasterDbScanResult` already in memory from the scan.
**Fix:** The scan now stores the full `MasterDbScanResult` object in `_last_scan_result`. The ingest background task checks for this: if present, it reuses the already-computed fingerprints and ANLZ data to classify tracks and create sidecars directly (seconds instead of minutes). Falls back to full `ingest_from_master_db()` only when no prior scan exists.
**Files:** `scue/api/local_library.py`

### Quick-tier batch analysis extremely slow (~1 track/min for 1067 tracks)
Date: 2026-04-02
Milestone: N/A
**Symptom:** Batch quick analysis of 1067 tracks processed only ~60 tracks in ~30 minutes. Quick tier is supposed to be fast heuristic analysis (~3-7s per track), so 1067 tracks should take ~1-2 hours at most, not potentially 17+ hours at observed rate.
**Root Cause:** Not yet diagnosed. Possible causes: sequential processing of `quick_needs_base` tracks (tracks without base analysis run one at a time with GC between each), GIL contention from ThreadPoolExecutor, or I/O bottleneck reading audio files.
**Fix:** TBD — needs profiling of `_run_strata_batch` to identify bottleneck.
**Files:** `scue/api/strata.py` (`_run_strata_batch`)
