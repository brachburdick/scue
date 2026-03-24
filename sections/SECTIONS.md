# SCUE Section Map

> Defines the review sections, their boundaries, and coupling relationships.
> Each section has a 1-page contract in this directory.
> Sections are defined by real dataflow boundaries, not just folders.

## Sections

| Section | Contract | Owns | Test Command |
|---------|----------|------|-------------|
| bridge | [bridge.md](bridge.md) | `scue/bridge/`, `scue/network/`, `tests/test_bridge/` | `.venv/bin/python -m pytest tests/test_bridge/ -v` |
| analysis | [analysis.md](analysis.md) | `scue/layer1/`, `tests/test_layer1/` | `.venv/bin/python -m pytest tests/test_layer1/ -v` |
| pipeline | [pipeline.md](pipeline.md) | `scue/layer2/`, `scue/layer3/`, `scue/layer4/` | *(no tests yet — skeleton)* |
| server | [server.md](server.md) | `scue/api/`, `scue/config/`, `scue/main.py`, `scue/project/`, `scue/ui/` | `.venv/bin/python -m pytest tests/test_api/ -v` *(when exists)* |
| frontend | [frontend.md](frontend.md) | `frontend/` | `cd frontend && npm run typecheck && npm run build` |

## Coupling Map

```
bridge ──(DeviceInfo, PlayerState)──> analysis
analysis ──(TrackAnalysis, TrackCursor)──> server (via API imports)
bridge ──(BridgeManager, MessageRecorder)──> server (via API imports)
server ──(REST + WebSocket JSON)──> frontend
```

## Parallelization Rules

| Section Pair | Parallel? | Reason |
|-------------|-----------|--------|
| bridge + frontend | Yes | No shared runtime state, different runtimes |
| bridge + analysis | Yes | Analysis mocks bridge types in tests |
| analysis + frontend | Yes | No direct coupling |
| bridge + server | **No** | Server wires BridgeManager singleton, shares WS state |
| analysis + server | **No** | Server imports Layer 1 internals, shares TrackStore/TrackCache |
| server + frontend | **No** | Frontend consumes server's API/WS; contract changes propagate |

## Three-Pass Review Model

1. **Section review** (parallel where safe): One agent per section, reviewing internals only.
2. **Boundary review** (sequential): One agent reviews interfaces between sections — types that cross boundaries, WebSocket message schemas, REST API contracts.
3. **Integration review** (sequential): One agent checks end-to-end flows against acceptance criteria, using section contracts as the map.

## When to Split a Section

A section should split when:
- It has >2000 LOC of implementation (not skeleton)
- Two sub-areas have independent test suites
- A natural dataflow boundary exists between sub-areas

The `pipeline` section (Layers 2-4) will split into `cues`, `effects`, and `output` when each has real code.
