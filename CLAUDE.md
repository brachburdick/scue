# SCUE

Automated lighting/laser/visual cue generation for live DJ sets.

## What This App Does

Analyzes EDM tracks offline, tracks live Pioneer DJ playback via Pro DJ Link, generates
semantic music events (section changes, beats, risers, etc.), maps those events to abstract
visual effects, and outputs control signals to DMX/OSC/MIDI hardware. The goal: a single DJ
can run a full light/laser/visual show with zero manual cue triggering.

## Stack
- Python 3.11+, FastAPI, asyncio
- librosa, allin1-mlx (Apple Silicon) for audio analysis
- ruptures for change-point detection
- SQLite for track data storage
- WebSocket for browser UI communication
- YAML for all configuration (effects, fixtures, routing, palettes)
- Pro DJ Link UDP protocol for Pioneer hardware (no beat-link-trigger)
- netifaces for network interface discovery

## Architecture (4 Layers)
- **Layer 1** — Track Analysis (offline 1A) + Live Playback Tracking (Pro DJ Link, 1B)
- **Layer 2** — Cue Generation (TrackCursor → semantic CueEvent stream)
- **Layer 3** — Effect Engine (CueEvents → abstract visual output)
- **Layer 4** — Hardware Output (abstract → DMX/OSC/MIDI) + Venue configuration

Full architecture:       `docs/ARCHITECTURE.md`
Interface contracts:     `docs/CONTRACTS.md`
Decision log:            `docs/DECISIONS.md`
Milestone status:        `docs/MILESTONES.md`
Known pitfalls:          `LEARNINGS.md`

## Commands
- `uvicorn scue.main:app --reload` — run dev server
- `python -m pytest tests/test_layer1/ -v` — run Layer 1 tests
- `python -m pytest tests/test_layer2/ -v` — run Layer 2 tests
- `python -m pytest tests/` — run all tests
- `python tools/mock_prodjlink.py` — replay captured Pro DJ Link packets
- `python tools/analyze_track.py <path>` — CLI: analyze a single track

## Code Style
- Type hints on all function signatures
- Dataclasses for all data models (not raw dicts)
- asyncio for all real-time paths
- Use `logging` module, not `print()` (existing code uses print — migrate as you touch files)
- Tests required for any new public function

## Critical Rules
- **NEVER** modify a layer's public interface without updating `docs/CONTRACTS.md`
- **NEVER** overwrite Pioneer-sourced data with SCUE-derived data; log divergence instead (see `scue/layer1/divergence.py`)
- All configuration lives in `config/`. No hardcoded values for effects, fixtures, routing, or palettes
- Layers communicate only through typed interfaces defined in `docs/CONTRACTS.md`. No layer imports another layer's internals
- When a task touches two layers, **stop and ask Brach** before proceeding
- When in doubt, read `docs/ARCHITECTURE.md` before making structural decisions

## Pioneer / Pro DJ Link Notes
- Hardware connects via CAT-5 on `en16` (link-local 169.254.x.x)
- macOS quirk: must use `IP_BOUND_IF=25` socket option (not unicast bind) to receive broadcasts — see `scue/layer1/prodjlink.py`
- Port 50001: device keepalive/announcement. Port 50000: CDJ status broadcasts
- No beat-link-trigger dependency — SCUE speaks Pro DJ Link directly

## Current State
See `docs/MILESTONES.md` for what's built and what's next.
Known issues and non-obvious patterns: `LEARNINGS.md` — read before starting work.
