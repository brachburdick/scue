# SCUE Section Map

> Defines the review sections, their boundaries, and coupling relationships.
> Each section has a 1-page contract in this directory.
> Sections are defined by real dataflow boundaries, not just folders.

## Sections

| Section | Contract | Owns | Test Command |
|---------|----------|------|-------------|
| bridge | [bridge.md](bridge.md) | `scue/bridge/`, `scue/network/`, `tests/test_bridge/` | `.venv/bin/python -m pytest tests/test_bridge/ -v` |
| analysis | [analysis.md](analysis.md) | `scue/layer1/{analysis,models,cursor,storage,tracking,waveform,enrichment,divergence,fingerprint}.py` | `.venv/bin/python -m pytest tests/test_layer1/test_analysis.py tests/test_layer1/test_cursor.py tests/test_layer1/test_enrichment.py tests/test_layer1/test_tracking.py tests/test_layer1/test_storage.py tests/test_layer1/test_divergence.py tests/test_layer1/test_fingerprint.py tests/test_layer1/test_models.py tests/test_layer1/test_analysis_edge_cases.py -v` |
| detectors | [detectors.md](detectors.md) | `scue/layer1/detectors/`, `scue/layer1/eval_detectors.py`, `config/detectors.yaml` | `.venv/bin/python -m pytest tests/test_layer1/test_flow_model.py tests/test_layer1/test_snap.py tests/test_layer1/test_percussion_stem.py -v` |
| ingestion | [ingestion.md](ingestion.md) | `scue/layer1/{scanner,usb_scanner,anlz_parser,rekordbox_scanner,reanalysis}.py`, `scue/api/{scanner,usb,local_library}.py` | `.venv/bin/python -m pytest tests/test_layer1/test_scanner.py tests/test_layer1/test_usb_scanner.py tests/test_layer1/test_anlz_parser.py tests/test_layer1/test_anlz_pssi.py tests/test_layer1/test_rekordbox_scanner.py -v` |
| strata | [strata.md](strata.md) | `scue/layer1/strata/`, `tests/test_layer1/test_strata_*` | `.venv/bin/python -m pytest tests/test_layer1/test_strata_sources.py tests/test_layer1/test_strata_standard.py tests/test_layer1/test_strata_priors.py -v` |
| pipeline | [pipeline.md](pipeline.md) | `scue/layer2/`, `scue/layer3/`, `scue/layer4/` | *(no tests yet — skeleton)* |
| server | [server.md](server.md) | `scue/api/`, `scue/config/`, `scue/main.py`, `scue/project/`, `scue/ui/` | `.venv/bin/python -m pytest tests/test_api/ -v` |
| frontend-core | [frontend-core.md](frontend-core.md) | `frontend/src/{layout,bridge,ingestion,tracks}/`, stores, api, types, utils, shell pages | `cd frontend && npm run typecheck && npm run build` |
| frontend-viz | [frontend-viz.md](frontend-viz.md) | `frontend/src/{analysis,annotations,detectors,live,strata,waveformTuning}/`, shared canvas, hooks, viz pages | `cd frontend && npm run typecheck && npm run build` |

## Coupling Map

```
bridge ──(DeviceInfo, PlayerState)──> analysis
bridge ──(DeviceInfo)──> ingestion (hardware scan context)
bridge ──(PlayerState)──> strata (via LiveStrataAnalyzer)
analysis ──(TrackAnalysis, Section)──> detectors (feature input)
analysis ──(TrackAnalysis, DrumPattern)──> strata
analysis ──(TrackStore)──> ingestion (track persistence target)
detectors ──(MusicalEvent, DrumPattern)──> analysis (detector output)
detectors ──(AtomicEvent, StemType)──> strata (type alignment)
strata ──(ArrangementFormula, LiveStrataAnalyzer)──> analysis (tracking.py only)
strata ──(StrataStore, StrataEngine)──> server (via api/strata.py)
analysis ──(TrackAnalysis, TrackCursor)──> server (via API imports)
ingestion ──(endpoint logic)──> server (co-owned API routers)
bridge ──(BridgeManager, MessageRecorder)──> server (via API imports)
server ──(REST + WebSocket JSON)──> frontend-core
frontend-core ──(stores, api, types)──> frontend-viz
```

## Parallelization Rules

| Section Pair | Parallel? | Reason |
|-------------|-----------|--------|
| bridge + frontend-core | Yes | No shared runtime state, different runtimes |
| bridge + frontend-viz | Yes | No shared runtime state, different runtimes |
| bridge + analysis | Yes | Analysis mocks bridge types in tests |
| bridge + detectors | Yes | No coupling |
| bridge + ingestion | Yes | Ingestion only uses DeviceInfo type |
| bridge + strata | Yes | Strata only uses PlayerState type |
| analysis + frontend-core | Yes | No direct coupling |
| analysis + frontend-viz | Yes | No direct coupling |
| detectors + ingestion | Yes | Zero coupling — independent subsystems |
| detectors + frontend-core | Yes | No direct coupling |
| detectors + frontend-viz | Yes | No direct coupling |
| detectors + strata | Yes | Only shared types, no runtime coupling |
| ingestion + strata | Yes | No coupling |
| ingestion + frontend-viz | Yes | No coupling |
| strata + frontend-core | Yes | No direct coupling |
| strata + frontend-viz | Yes | No direct coupling |
| analysis + detectors | **Caution** | analysis.py calls run_detectors() — review together if detector API changes |
| analysis + strata | **Caution** | tracking.py imports from strata — review together if live analysis boundary changes |
| analysis + ingestion | **Caution** | Ingestion writes to TrackStore that analysis reads — review if storage contract changes |
| frontend-core + frontend-viz | **Caution** | Viz consumes core's stores/types — review together if store or type shapes change |
| bridge + server | **No** | Server wires BridgeManager singleton, shares WS state |
| analysis + server | **No** | Server imports Layer 1 internals, shares TrackStore/TrackCache |
| strata + server | **No** | Server imports StrataStore/StrataEngine via api/strata.py |
| ingestion + server | **No** | Co-owned API routers — changes must be coordinated |
| server + frontend-core | **No** | Frontend consumes server's API/WS; contract changes propagate |

## Three-Pass Review Model

1. **Section review** (parallel where safe): One agent per section, reviewing internals only.
2. **Boundary review** (sequential): One agent reviews interfaces between sections — types that cross boundaries, WebSocket message schemas, REST API contracts.
3. **Integration review** (sequential): One agent checks end-to-end flows against acceptance criteria, using section contracts as the map.

## When to Split or Merge Sections

A section should **split** when:
- It has >2000 LOC of implementation (not skeleton)
- Two sub-areas have independent test suites
- A natural dataflow boundary exists between sub-areas

A section should **merge** when:
- Two sections share runtime state that can't be cleanly injected
- Changes to one section routinely require changes to the other
- The boundary contract between them is more complex than either section's internals

**Re-evaluate sections after each session batch.** New features, refactors, or milestone completions may shift where the real boundaries are. Section structure is a living artifact, not a one-time decision.

## Future Split Candidates

- **pipeline** → `cues`, `effects`, `output` when each sub-layer has >500 LOC and its own test suite
- **server** → split API routers by domain if `scue/api/` exceeds 5K LOC of endpoint logic
- **frontend-viz** → split waveform/canvas from strata/arrangement if they diverge in skill requirements
