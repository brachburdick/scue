# Section: server

## Purpose
FastAPI application, API routers, WebSocket broadcasting, configuration loading, and runtime wiring. This is the integration point where cross-section coupling is allowed and expected.

## Owned Paths
```
scue/api/           — REST + WS endpoints (tracks, strata, bridge, network, audio, usb, etc.)
scue/config/        — YAML config loading (ScueConfig, BridgeConfig, ServerConfig)
scue/main.py        — app factory, singleton wiring, callback registration
scue/project/       — project metadata
scue/ui/            — placeholder
```

## Incoming Inputs
- **From bridge section:** `BridgeManager` (lifecycle control), `MessageRecorder` (dev tooling)
- **From analysis section:** `TrackStore`, `TrackCache`, `PlaybackTracker`, `StrataStore` (singletons)
- **From analysis section:** `TrackAnalysis`, `MusicalEvent`, `DrumPattern`, serialization functions
- **From config files:** YAML configuration (bridge, server, analysis paths)

## Outgoing Outputs
- **REST API:** JSON responses matching `docs/CONTRACTS.md` types
- **WebSocket:** `bridge_status`, `pioneer_status`, `playback_position` messages to frontend
- **Background jobs:** `AnalysisJob` tracking for long-running analysis tasks

## Invariants
- API routers use lazy imports (inside endpoint functions) to avoid circular dependencies.
- `main.py` is the ONLY file that creates singletons and wires callbacks.
- No API router creates its own `TrackStore`, `BridgeManager`, etc. — all injected via `init_*_api()`.
- WebSocket broadcast is one-way (server → client). No client → server commands via WS.
- Background jobs are in-memory only (lost on server restart). Documented limitation.

## Allowed Dependencies
- `scue.bridge` — BridgeManager, MessageRecorder, BridgeAdapter
- `scue.layer1` — all public types and functions (this section is the integration point)
- `scue.config` — config loading
- `scue.network` — route management (exposed via API)
- Python stdlib, `fastapi`, `uvicorn`, `pydantic`

## How to Verify
```bash
# Typecheck:
cd frontend && npm run typecheck  # Verifies FE types match BE contract

# API tests (when they exist):
.venv/bin/python -m pytest tests/test_api/ -v

# Integration: start server and verify endpoints respond
.venv/bin/uvicorn scue.main:app --reload
```

## Review Notes
This section is where seam-bugs live. When reviewing:
- Check that `main.py` wiring matches what API routers expect
- Check that WebSocket message shapes match `frontend/src/types/ws.ts`
- Check that lazy imports inside endpoints match the public API of their source sections
- Check that singleton lifecycle (create → wire → cleanup) is correct across restart scenarios
