# Project Observations — SCUE

<!-- Format: - [TYPE] Description. (from: self-assessment, <model>, <date>) -->
<!-- Types: A1=code quality, A2=convention drift, A3=architecture, A4=documentation gap -->
<!-- Per v2 self-assessment prompt: these are about the code/architecture/project itself -->
<!-- Pipeline root causes (B6 links) live in PROTOCOL_IMPROVEMENTS.md -->
<!-- Max 7 entries per self-assessment. Consolidated per v2 prompt. -->

- [A1] `bridge/manager.py` pipes Java subprocess stderr but never drains it — all Java runtime errors and exception traces are silently lost. No JUnit or integration test coverage exists for `BeatLinkBridge.java` (all 169 bridge tests are Python-side), so bugs like the BLUE-style `emitTrackWaveform` crash can only be caught by live hardware QA. (from: self-assessment, claude-opus-4-6, 2026-03-22)

- [A3] Track analysis does not populate `track_ids` — only USB scanning creates `(source_player, source_slot, rekordbox_id) → fingerprint` mappings. Two parallel track resolution paths now exist (bridge MetadataFinder vs USB scan rbox) with no documented precedence or conflict resolution when both provide metadata for the same track. (from: self-assessment, claude-opus-4-6, 2026-03-22)

- [A3] `bridge/manager.py` health check uses wall-clock `time.time()` that false-positives during macOS display sleep; frontend `ws.ts` reconnect backoff accumulates across sleep cycles without resetting on `visibilitychange`. Both are the same class of bug — system-level timer drift with no monotonic-clock or oversleep guard. (from: self-assessment, claude-opus-4-6, 2026-03-22)

- [A4] Multiple stale references after beat-link 8.1.0-SNAPSHOT upgrade: ADR-014 ("WaveformFinder broken on ALL DLP"), ADR-012 comment in `BeatLinkBridge.java:17`, `adapter.py:243` comment ("bridge doesn't send track_metadata"), and `research/waveform-finder-hardware-compatibility.md` XDJ-AZ entry — all outdated but uncorrected. (from: self-assessment, claude-opus-4-6, 2026-03-22)

- [A4] `WaveformDetail` has three styles (`BLUE`/`RGB`/`THREE_BAND`) with different API surfaces — `segmentHeight(i, max, ThreeBandLayer)` throws `UnsupportedOperationException` on non-THREE_BAND. No documentation records which styles exist, which hardware sends which, or which overloads are safe per style. The discriminator is `detail.style` (enum), not `isColor` (boolean). (from: self-assessment, claude-opus-4-6, 2026-03-22)

- [A2] `_ensure_device_from_player()` in `adapter.py:406` hardcodes `uses_dlp=True` — will produce wrong metadata resolution for legacy CDJs (CDJ-2000NXS2, CDJ-3000) that connect without a prior `device_found` message. (from: self-assessment, claude-opus-4-6, 2026-03-22)

- [A2] Batch analysis has no documented max batch size or user-facing limit. 130-file upload partially failed with no clear error surfaced; `complete_with_errors` status was added but root cause (likely server timeout or memory) never diagnosed. (from: self-assessment, claude-opus-4-6, 2026-03-22)

<!-- Below: items moved from PROTOCOL_IMPROVEMENTS.md during v2.0 cleanup (pipeline → project) -->

- [A1] Bridge JAR rebuild requires 5 manual steps: edit Java → `./gradlew shadowJar` → copy JAR to `lib/` → kill old bridge PID → restart Python backend. No script automates this cycle. Stale bridge processes accumulate if not explicitly killed. (from: v2.0 cleanup, originally self-assessment 2026-03-22)

- [A3] Health check `time.time()` false-positives during macOS display sleep. Frontend WS reconnect backoff accumulates across sleep cycles without resetting on `visibilitychange`. No architectural doc maps which components have timers, heartbeats, or liveness checks. (from: v2.0 cleanup, originally self-assessment 2026-03-22)

- [A4] ADR-012 blanket-disabled all Finders based on beat-link v8.0.0, but 8.1.0-SNAPSHOT (used since Aug 2025) fixed XDJ-AZ support. ADR was never re-evaluated when upstream changed. No convention triggers ADR review when dependencies evolve. (from: v2.0 cleanup, originally self-assessment 2026-03-22)

- [A1] QA with Chrome extension requires ambiguous connection setup — no startup diagnostic confirms browser automation readiness before beginning QA workflow. (from: v2.0 cleanup, originally self-assessment 2026-03-22)
