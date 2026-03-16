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

## Completed: Milestone 1 — Analysis Pipeline (Layer 1A, Tier 1)
Status: COMPLETE
Started: 2026-03-16
Completed: 2026-03-16

### Deliverables
- [x] Section segmentation with allin1-mlx (+ librosa-only fallback)
- [x] 8-bar snapping pass
- [x] EDM flow model labeler
- [x] JSON file storage keyed by track fingerprint (SHA256)
- [x] SQLite cache (derived index)
- [x] Fakeout detection
- [x] RGB waveform computation (3-band: bass/mids/highs at 60fps)
- [x] Test suite against 5 reference tracks (57 tests, all passing)

### Acceptance Criteria — All Passing
- Pipeline analyzes audio → sections, beats, downbeats, features, waveform
- Sections are 8-bar snapped with irregular phrase flagging
- EDM flow model relabels to intro/verse/build/drop/breakdown/fakeout/outro
- JSON files persist as source of truth; SQLite is derived cache
- All 5 reference tracks produce valid section segmentations
- TrackAnalysis schema includes enrichment fields (null) from day one
- REST API: GET /api/tracks, GET /api/tracks/{fp}, POST /api/tracks/analyze
- CLI tool: python tools/analyze_track.py <path>

### Notes
- allin1-mlx gracefully skipped when not installed; falls back to librosa-only with ruptures
- Sections clamped: first starts at 0.0, last ends at track duration
- Running without allin1-mlx: confidence is lower (scaled by 0.7), all sections derived from ruptures change-point detection
- Pipeline takes ~3-4s per track on M-series Mac (without allin1-mlx)

---

## Backlog

### ~~Milestone FE-3 — Track Table (Read-Only)~~ → COMPLETE (2026-03-16)
- [x] TanStack Table with 10 sortable columns (Title, Artist, BPM, Key, Duration, Sections, Mood, Source, Analyzed, ID)
- [x] Client-side search filtering by title/artist
- [x] Mood badges (color-coded) and Source badges (analysis vs enriched)
- [x] TanStack Query integration with Vite API proxy
- [x] QueryClientProvider wired into app root
- [x] TypeScript types mirroring Python models (src/types/track.ts)

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
### ~~Milestone FE-4 — Upload & Analyze Flow~~ → COMPLETE (2026-03-16)
- [x] Path-based scan → batch analyze → progress tracking flow
- [x] `POST /api/tracks/scan` — directory scanning with fingerprint-based dedup
- [x] `POST /api/tracks/analyze-batch` — sequential background analysis with in-memory job tracking
- [x] `GET /api/tracks/jobs/{job_id}` — job status polling (1s interval, auto-stops on completion)
- [x] `GET /api/filesystem/browse` — server-side filesystem browser (separate router)
- [x] AnalyzePanel: 3-phase UI (path input → scan results → progress bar)
- [x] FolderBrowser modal: breadcrumb navigation, directory/audio-file listing
- [x] Auto-dismiss on completion: resets to path input after 2s delay
- [x] Zustand store for analyze flow state (analyzeStore.ts)
### Milestone FE-5 — Track Management + Projects
### Milestone FE-6 — Enrichment + Logs + Network Pages
### Milestone 7 — Event Detection (Layer 1A, Tier 2)
### Milestone 8 — Full Cue Vocabulary
### Milestone 9 — OSC Visual Output (Layer 4B)
### Milestone 10 — Real-Time User Override UI (Layer 4C)
### Milestone 11 — Polish & Tier 3 Features
