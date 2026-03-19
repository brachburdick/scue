# Task Spec: API-Level Test Coverage (Justified Subset)

**Source:** Audit 2026-03-17, Domain D (API/Config)
**Priority:** Gap — but scoped to high-value tests only
**Touches:** `tests/test_api/` (NEW directory)
**Layer boundary:** API layer only — tests mock Layer 0 and Layer 1

## Philosophy

The project has strong unit test coverage for Layer 0 (bridge) and Layer 1 (analysis + tracking). Adding API tests is valuable **only where the API layer adds logic beyond simple delegation**. We should NOT test:

- Endpoints that just call `store.load(fp)` and return the result (pure passthrough)
- Endpoints that just return a static status dict
- Anything already covered by the bridge/layer1 test suites

We SHOULD test:

- **Endpoints with business logic** in the API layer itself
- **State mutation sequences** that wire multiple components together
- **WebSocket message flow** (the broadcasting pipeline)
- **Error paths** that the API layer handles (404s, validation, malformed input)

## Justified Test Cases

### 1. Batch Analysis Job Lifecycle (HIGH VALUE)

**Why:** `api/tracks.py` + `api/jobs.py` contain an in-memory job tracker with state machine logic (`pending → running → complete/failed`). This is API-layer logic not tested anywhere else.

**Tests:**
- [ ] POST `/api/tracks/analyze-batch` creates job, returns job_id
- [ ] GET `/api/tracks/jobs/{job_id}` returns correct state progression
- [ ] Job with invalid paths → individual file errors, job still completes
- [ ] Job with empty file list → immediate completion
- [ ] GET `/api/tracks/jobs/{bad_id}` → 404

### 2. Directory Scan Deduplication (HIGH VALUE)

**Why:** `api/tracks.py` scan endpoint checks fingerprints against the cache to report `new_files` vs `already_analyzed`. This dedup logic lives in the API layer.

**Tests:**
- [ ] POST `/api/tracks/scan` with mix of new and existing tracks → correct counts
- [ ] POST `/api/tracks/scan` with non-existent path → error response
- [ ] POST `/api/tracks/scan` with empty directory → zero files

### 3. Bridge Settings Update + Restart Sequence (MEDIUM VALUE)

**Why:** PUT `/api/bridge/settings` writes YAML, POST `/api/bridge/restart` reads it. The sequence matters — settings must persist before restart picks them up.

**Tests:**
- [ ] PUT settings → YAML file updated on disk
- [ ] PUT settings with invalid port (< 1024) → validation error
- [ ] POST restart → manager.stop() + manager.start() called in sequence

### 4. WebSocket Bridge State Broadcasting (MEDIUM VALUE)

**Why:** The pipeline `bridge state change → WSManager.broadcast() → all connected clients receive JSON` is the primary real-time path. It's wired in `main.py` and exercises `ws_manager.py`.

**Tests:**
- [ ] Connect WebSocket → receive initial `bridge_status` message
- [ ] Bridge state change → connected clients receive update
- [ ] Client disconnect → removed from broadcast set (no errors on next broadcast)

### 5. Network Route Endpoints (LOW VALUE — only if time permits)

**Why:** These are mostly passthrough to `network/route.py` which is well-tested. Only worth testing the API layer's response formatting and error wrapping.

**Tests:**
- [ ] GET `/api/network/route` on non-macOS → `route_applicable: false`
- [ ] POST `/api/network/route/fix` without sudoers → appropriate error

## What We Are NOT Testing (and why)

| Endpoint | Why skip |
|----------|----------|
| `GET /api/tracks` | Passthrough to `cache.list_tracks()` — tested in L1 |
| `GET /api/tracks/{fp}` | Passthrough to `store.load()` — tested in L1 |
| `GET /api/bridge/status` | Passthrough to `manager.to_status_dict()` — tested in L0 |
| `GET /api/usb/status` | Returns stored scan result — trivial |
| `GET /api/usb/pioneer-metadata` | Passthrough to `cache.list_pioneer_metadata()` — tested in L1 |
| `GET /api/filesystem/browse` | Thin `os.listdir()` wrapper — low risk |
| `GET /api/health` | Returns `{"status": "ok"}` — not worth a test |

## Implementation Notes

- Use FastAPI's `TestClient` (from `httpx`) for synchronous endpoint testing
- Mock `BridgeManager` and `TrackStore`/`TrackCache` — API tests should not require Java, audio files, or SQLite
- Use `pytest-asyncio` for WebSocket tests
- Place all tests in `tests/test_api/`

## Estimated Scope

~200-300 lines of test code. About 15-20 test functions across 2-3 test files:
- `tests/test_api/test_tracks_api.py` — batch jobs + scan dedup
- `tests/test_api/test_bridge_api.py` — settings + restart + WebSocket
- `tests/test_api/test_network_api.py` — route endpoints (optional)

## Acceptance Criteria

- All justified tests pass
- Tests run in < 5s (no real subprocess, no audio analysis)
- Tests are independent (no shared state between test functions)
- No mocking of things that should be tested (i.e., mock Layer 0/1, test API logic)
