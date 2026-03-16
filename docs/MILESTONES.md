# Milestones

## Completed: Milestone FE-1 — Shell + Routing (no backend dependency)
Status: COMPLETE
Started: 2026-03-16
Completed: 2026-03-16

### Deliverables
- [x] Vite + React + TS + Tailwind scaffolded
- [x] Shell layout (sidebar, top bar, content outlet, console stub)
- [x] React Router with all routes
- [x] Placeholder pages (Tracks, BLT, Enrichment, Logs, Network)

### Acceptance criteria — all passing
- App renders
- Navigation works
- Console toggles
- Sidebar highlights active page

### Notes
- Used Vite 6 (not 8) due to Node 20.18 compatibility. Vite 8 requires Node 20.19+.
- Tailwind v3 (not v4) due to peer dependency conflicts with Vite 6.

---

## Current: Milestone 1 — Analysis Pipeline (Layer 1A, Tier 1)
Status: NOT STARTED

### Deliverables
- [ ] Section segmentation with allin1-mlx
- [ ] 8-bar snapping pass
- [ ] EDM flow model labeler
- [ ] JSON file storage keyed by track fingerprint
- [ ] SQLite cache (derived index)
- [ ] Fakeout detection
- [ ] Visual QA tool (RGB waveform + section markers)
- [ ] Test suite against 5 reference tracks

### Notes
- TrackAnalysis schema must include enrichment fields (null initially) from day one
- Design for Pioneer enrichment compatibility even though bridge isn't built yet

---

## Backlog

### Milestone FE-3 — Track Table (Read-Only)
- TanStack Table with sorting, filtering, status indicators
- Loads from GET /api/tracks

### Milestone 0 — Beat-Link Bridge (Layer 0)
- Java bridge JAR + Python manager + adapter + fallback

### Milestone 2 — Live Cursor + Pioneer Enrichment (Layer 1B)
- Consume bridge data → PlaybackState + TrackCursor
- Pioneer enrichment pass on first track load
- Divergence logging

### Milestone 3 — Cue Stream (Layer 2, section cues only)
### Milestone 4 — Basic Effect Engine (Layer 3A + 3B, minimal)
### Milestone 5 — DMX Output (Layer 4A + 4B)
### Milestone 6 — End-to-End Demo
### Milestone FE-2 — WebSocket + Console + Bridge Status
### Milestone FE-4 — Upload & Analyze Flow
### Milestone FE-5 — Track Management + Projects
### Milestone FE-6 — Enrichment + Logs + Network Pages
### Milestone 7 — Event Detection (Layer 1A, Tier 2)
### Milestone 8 — Full Cue Vocabulary
### Milestone 9 — OSC Visual Output (Layer 4B)
### Milestone 10 — Real-Time User Override UI (Layer 4C)
### Milestone 11 — Polish & Tier 3 Features
