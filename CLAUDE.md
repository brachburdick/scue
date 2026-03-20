# SCUE

Automated lighting/laser/visual cue generation for live DJ sets.

## Key References
-   Domain skills: `skills/`
-   Feature specs & plans: `specs/feat-[name]/`
-   Research findings: `research/`
-   Protocol improvement proposals: `docs/agents/PROTOCOL_IMPROVEMENT.md`


## Stack
- Python 3.11+, FastAPI, asyncio
- beat-link (Java library) via managed subprocess for Pro DJ Link protocol
- librosa, allin1-mlx for audio analysis
- JSON files (source of truth) + SQLite (derived cache) for track data
- React 19 + TypeScript (strict) + Vite + Tailwind for frontend
- Zustand for FE state, TanStack Query/Table for data fetching/display
- WebSocket for real-time FE/BE communication, REST for CRUD
- YAML for all configuration (effects, fixtures, routing, palettes)

## Architecture (5 Layers + Frontend)
- Layer 0: Beat-link bridge (Java subprocess → WebSocket → Python adapter)
- Layer 1: Track analysis (offline) + live playback tracking (via bridge)
- Layer 2: Cue generation (music events → semantic cue stream)
- Layer 3: Effect engine (cues → abstract visual output)
- Layer 4: Output & hardware (abstract → DMX/OSC/MIDI) + venue config
- Frontend: React/TS app (Tracks, BLT, Enrichment, Logs, Network pages)

Full architecture: docs/ARCHITECTURE.md
Interface contracts between layers: docs/interfaces.md
Decision log: docs/DECISIONS.md

## Commands
### Backend
- `python -m pytest tests/test_bridge/` — bridge tests
- `python -m pytest tests/test_layer1/` — Layer 1 tests
- `python -m pytest tests/` — all tests
- `uvicorn scue.main:app --reload` — run dev server
- `python tools/mock_bridge.py` — replay captured bridge messages

### Frontend
- `cd frontend && npm run dev` — run frontend dev server
- `cd frontend && npm run build` — production build
- `cd frontend && npm run typecheck` — TypeScript type checking

## Code Style
### Python
- Type hints on all function signatures
- Dataclasses for all data models (not raw dicts)
- asyncio for all real-time paths
- No print() — use logging module
- Tests required for any new public function

### TypeScript
- Strict mode enabled
- All FE/BE boundary types defined in frontend/src/types/
- Zustand stores are independent — no store imports another store

## Critical Rules
- NEVER modify a layer's public interface without updating docs/interfaces.md
- NEVER overwrite Pioneer-sourced data with SCUE-derived data; log divergence instead
- NEVER import across layer boundaries except through the defined contracts
- All configuration is YAML files in config/. No hardcoded values.
- Track analysis JSON files are the source of truth. SQLite is a derived cache only.
- When in doubt, read docs/ARCHITECTURE.md before making structural decisions
- If a task touches two layers, stop and ask Brach before proceeding

## Current State
See docs/MILESTONES.md for what's built and what's next.

## Bug Tracking
When a bug is found and fixed, record it in the appropriate log under `docs/bugs/`:
- `docs/bugs/frontend.md` — React/TS/Vite/Tailwind
- `docs/bugs/layer0-bridge.md` — Beat-link bridge
- `docs/bugs/layer1-analysis.md` — Track analysis & live tracking
- `docs/bugs/layer2-cues.md` — Cue generation
- `docs/bugs/layer3-effects.md` — Effect engine
- `docs/bugs/layer4-output.md` — Output & hardware

Every fix gets an entry: symptom, root cause, fix, and affected file(s). No fix is too small to record.

## Flow Skills
Flow skills (debug flow, feature flow, refactor flow) are inherited from the portfolio level
(`THE_FACTORY/skills/`). SCUE does not duplicate them.

**SCUE-specific debug rule:** During the **Isolate** phase of any debug task, if the bug could
involve Layer 3 (effect engine) or Layer 4 (output/hardware), always check DMX output state.
Verify fixture addresses, universe assignments, and whether the DMX frame buffer reflects
expected values before moving to Diagnose.

## Known Issues & Patterns
See LEARNINGS.md — read it before starting work.
See docs/bugs/ — per-layer bug logs for historical fixes.
