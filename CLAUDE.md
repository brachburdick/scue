# SCUE

Automated lighting/laser/visual cue generation for live DJ sets.

## Key References
-   Domain skills: `skills/`
-   Feature specs & plans: `specs/feat-[name]/`
-   Research findings: `research/` (also check portfolio-level `support/research/` at repo root)
-   Protocol improvement proposals: `docs/agents/PROTOCOL_IMPROVEMENT.md`

## ADR Convention
When an ADR is superseded by a newer decision, add a banner at the top:
```
> **SUPERSEDED** by [ADR-0XX](link). The conclusions below may no longer apply.
```
When a dependency upgrade invalidates an ADR's assumptions, the upgrade commit should update or supersede the affected ADR.


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
- `.venv/bin/python -m pytest tests/test_bridge/` — bridge tests
- `.venv/bin/python -m pytest tests/test_layer1/` — Layer 1 tests
- `.venv/bin/python -m pytest tests/` — all tests
- `.venv/bin/uvicorn scue.main:app --reload` — run dev server
- `.venv/bin/python tools/mock_bridge.py` — replay captured bridge messages

### Frontend
- `cd frontend && npm run dev` — run frontend dev server
- `cd frontend && npm run build` — production build
- `cd frontend && npm run typecheck` — TypeScript type checking

## Trigger Table

| Task Pattern | Skill Location | Notes |
|---|---|---|
| SCUE session start / any SCUE work | `skills/codebase-orientation.md` | Load first. File map, data flows, gotchas. |
| Audio analysis / beatgrid / rekordbox | `skills/audio-analysis.md` | Pioneer/Serato metadata |
| Beat-link bridge / Pro DJ Link | `skills/beat-link-bridge.md` | Lifecycle, messages, API reference |
| Pioneer hardware / CDJ / XDJ / DJM | `skills/pioneer-hardware.md` | Hardware variants, device specifics |
| Frontend / React / TypeScript / Zustand | `skills/react-typescript-frontend.md` | SCUE component patterns |
| Python / FastAPI / asyncio backend | `skills/python-fastapi.md` | Routers, testing, async patterns |
| Waveform rendering / frequency color / amplitude scaling | `skills/waveform-rendering.md` | Psychoacoustics, Pioneer parity, preset system |
| Editing WaveformCanvas / AnnotationTimeline / DeckWaveform | `skills/component-api-reference.md` | Props, draw pipeline, interactions |
| Section review / boundary review / scoped review | `sections/SECTIONS.md` | Section map, contracts, coupling rules |

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

## Windows Compatibility (Goal)
SCUE is macOS-first but targets Windows compatibility. The goal is to avoid a massive rewrite
later — not to maintain OS parity at every step.

**Guiding rule:** Do not introduce new macOS-only dependencies without a known Windows alternative.

**Known platform-specific areas:**
- `allin1-mlx` — MLX is Apple Silicon only. Will need PyTorch/ONNX backend on Windows.
- macOS route fixing (`tools/install-route-fix.sh`, launchd, sudoers) — already platform-guarded.
- JVM flags (`-Dapple.awt.UIElement`, `-Xdock:name`) — need platform conditional.
- Shell scripts are bash-only — `gradlew.bat` covers the Java build; route scripts are macOS-only.

**Phases:**
0. Audit + document (done). Avoid new platform-locked deps.
1. Get app running on Windows (frontend + backend + bridge).
2. Platform-specific feature parity (route fixing alternative, MLX alternative).
3. CI/packaging for Windows.

## Test Audio Fixtures
Audio test assets live in `tests/fixtures/audio/` (gitignored — binary files, not checked in).
See `tests/fixtures/audio/MANIFEST.md` for the full inventory of what's needed and why.

Categories: full-tracks, loops, one-shots, stems, edge-cases, pioneer enrichment, format variants.
Synthetic generators exist in `tests/test_layer1/test_analysis_edge_cases.py`.

## Known Issues & Patterns
Read BOTH before starting work:
- `LEARNINGS.md` — SCUE-specific project/domain knowledge (bridge, layers, hardware)
- `../../LEARNINGS.md` — workspace/toolchain knowledge (Node, Vite, Tailwind, Python venv, Langfuse)
See docs/bugs/ — per-layer bug logs for historical fixes.
