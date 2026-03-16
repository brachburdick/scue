# SCUE

**Automated lighting, laser, and visual cue generation for live DJ sets.**

SCUE analyzes EDM tracks offline, tracks live Pioneer DJ playback via Pro DJ Link (no middleware required), generates semantic music events, maps those events to abstract lighting effects, and outputs control signals to DMX/OSC/MIDI hardware. The goal: a single DJ can run a full light/laser/visual show with zero manual cue triggering.

---

## Current Status

**Milestone 1 (in progress):** Audio analysis pipeline — section segmentation, EDM labeling, RGB waveform visualizer.

**Milestone 2 (in progress):** Pioneer Pro DJ Link integration — real-time BPM, beat position, deck status via direct UDP.

See `docs/MILESTONES.md` for the full roadmap.

---

## Architecture

```
Audio → [Layer 1: Analysis + Live Tracking]
              ↓ TrackCursor
         [Layer 2: Cue Generation]
              ↓ CueEvent stream
         [Layer 3: Effect Engine]
              ↓ abstract FixtureOutput
         [Layer 4: Hardware Output → DMX / OSC / MIDI]
```

Full details: `docs/ARCHITECTURE.md`

---

## Quickstart

```bash
# Install dependencies (Python 3.11+, Apple Silicon Mac)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start the server
uvicorn scue.main:app --reload

# Open the browser UI
open http://localhost:8000
```

**Pioneer hardware:** Connect via CAT-5 ethernet. SCUE auto-discovers Pioneer devices on link-local interfaces (169.254.x.x). No beat-link-trigger required.

**Model weights (first-time):** If you see "Could not find MLX weights for harmonix-fold0", run:
```bash
python scripts/download_mlx_weights.py
```

---

## Project Structure

```
scue/                          # project root
├── CLAUDE.md                  # AI agent instructions (root — loaded every session)
├── LEARNINGS.md               # Append-only log of non-obvious discoveries
├── docs/
│   ├── ARCHITECTURE.md        # Full architecture plan
│   ├── MILESTONES.md          # Current milestone status
│   ├── DECISIONS.md           # Architectural decision records
│   └── CONTRACTS.md           # Interface contracts between layers
├── config/
│   ├── venues/                # Venue layout YAML files
│   ├── routing/               # Effect routing preset YAML files
│   ├── effects/               # Effect definition YAML files
│   ├── fixtures/              # Fixture profile YAML files
│   └── palettes/              # Color palette YAML files
├── scue/                      # Python package
│   ├── main.py                # FastAPI app entry point
│   ├── layer1/                # Track analysis + Pioneer integration
│   ├── layer2/                # Cue generation (stub — Milestone 3)
│   ├── layer3/                # Effect engine (stub — Milestone 4)
│   ├── layer4/                # Hardware output (stub — Milestone 5)
│   └── ui/                    # Browser UI + WebSocket handlers
├── tests/
│   ├── fixtures/              # Test audio files, packet captures
│   ├── test_layer1/
│   └── ...
└── tools/                     # CLI utilities
    ├── analyze_track.py       # Analyze a track from the command line
    ├── mock_prodjlink.py      # Replay captured Pioneer packets (stub)
    ├── cue_visualizer.py      # Visualize cue stream output (stub)
    └── venue_preview.py       # 2D fixture preview (stub)
```

---

## Development Commands

```bash
# Run the server
uvicorn scue.main:app --reload

# Run all tests
python -m pytest tests/ -v

# Run fast tests only (no audio fixtures needed)
python -m pytest tests/ -v -m "not slow"

# Analyze a track from CLI
python tools/analyze_track.py path/to/track.mp3

# Pioneer connectivity diagnostics
curl http://localhost:8000/api/pioneer/debug
```

---

## For AI Agents

Read `CLAUDE.md` first. Each layer has its own `CLAUDE.md` auto-loaded when working in that directory. Read `docs/CONTRACTS.md` before modifying any inter-layer interfaces. Read `LEARNINGS.md` before starting any work.
