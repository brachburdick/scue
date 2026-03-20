# Handoff Packet: FE-LIVE-DECK-MONITOR-TASKS

---
status: APPROVED
project_root: /Users/brach/Documents/THE_FACTORY/projects/DjTools/scue
revision_of: none
supersedes: none
superseded_by: none
---

## Dispatch
- Mode: ORCHESTRATOR DISPATCH
- Output path: `specs/feat-FE-live-deck-monitor/tasks.md`
- Parallel wave: none

## Objective
Produce an atomized task breakdown (with dependency graph, acceptance criteria per task, and file scope) for the FE-Live-Deck-Monitor feature, covering both backend contract changes and frontend implementation.

## Role
Architect

## Working Directory
- Run from: `/Users/brach/Documents/THE_FACTORY/projects/DjTools/scue`
- Related feature/milestone: FE-Live-Deck-Monitor

## Scope Boundary
- Files this agent MAY read:
  - `AGENT_BOOTSTRAP.md`
  - `preambles/ARCHITECT.md`, `preambles/COMMON_RULES.md`
  - `LEARNINGS.md`
  - `specs/feat-FE-live-deck-monitor/spec.md`
  - `specs/feat-FE-live-deck-monitor/design/ui-state-behavior.md`
  - `specs/feat-FE-analysis-viewer/tasks.md` — reference for task format and granularity
  - `specs/feat-FE-analysis-viewer/spec.md` — for shared component awareness
  - `frontend/src/types/bridge.ts` — current PlayerInfo type
  - `frontend/src/types/track.ts` — TrackAnalysis, Section types
  - `frontend/src/api/tracks.ts` — existing hooks (useTrackAnalysis, useTracks)
  - `frontend/src/stores/bridgeStore.ts` — bridge state shape
  - `frontend/src/components/shared/WaveformCanvas.tsx` — shared component props
  - `frontend/src/components/shared/PlaceholderPanel.tsx`
  - `frontend/src/components/analysis/` — existing Analysis Viewer components for pattern reference
  - `frontend/src/pages/AnalysisViewerPage.tsx` — thin page pattern
  - `frontend/CLAUDE.md` — frontend conventions
  - `docs/interfaces.md` — current bridge_status contract
  - `docs/CONTRACTS.md` — cross-layer contracts
  - `scue/bridge/manager.py` — to_status_dict() for backend contract change scoping
  - `scue/bridge/messages.py` — PlayerStatusPayload (track_source_player/slot already parsed)
  - `scue/layer1/storage.py` — track_ids table for migration scoping
  - `scue/api/tracks.py` — existing track endpoints
  - `templates/tasks.md` — task template (if exists)
- Files this agent must NOT touch:
  - Any code files (Architect is read-only)
  - `docs/agents/orchestrator-state.md`

## Context Files
- `AGENT_BOOTSTRAP.md` — read first
- `specs/feat-FE-live-deck-monitor/spec.md` — the full spec with backend contract changes, component hierarchy, data flow
- `specs/feat-FE-live-deck-monitor/design/ui-state-behavior.md` — Designer artifact with all component states
- `specs/feat-FE-analysis-viewer/tasks.md` — reference for task format, acceptance criteria style, dependency graph format

## Interface Contracts
- `docs/interfaces.md` — current bridge_status contract (PlayerInfo fields)
- `docs/CONTRACTS.md` — cross-layer contracts
- The spec defines new backend contract changes: `playback_position_ms`, `track_source_player`, `track_source_slot` in PlayerInfo, plus `GET /api/tracks/resolve/{source_player}/{source_slot}/{rekordbox_id}` endpoint, plus `track_ids` table migration.

## Required Output
- Write: `specs/feat-FE-live-deck-monitor/tasks.md`
- Write: `specs/feat-FE-live-deck-monitor/sessions/session-001-architect.md` (session summary)

## Constraints
- Tasks must cover BOTH backend changes (contract changes, new endpoint, DB migration) and frontend implementation.
- Backend tasks must precede frontend tasks in the dependency graph.
- Shared components (WaveformCanvas, SectionIndicator, useTrackAnalysis) are already built by FE-Analysis-Viewer — do NOT re-create them.
- New frontend components: DeckPanel, DeckWaveform, DeckMetadata, SectionIndicator (already shared), DeckEmptyState, LiveDeckMonitorPage.
- New backend: PlayerInfo extension, resolve endpoint, track_ids migration.
- Task granularity should match FE-Analysis-Viewer tasks (30-45 min effort per task).
- Each task must have: scope (files to create/modify), inputs, outputs, acceptance criteria, dependencies, context files.

## Acceptance Criteria
- [ ] Tasks file covers all backend contract changes from the spec
- [ ] Tasks file covers all frontend components from the spec's component hierarchy
- [ ] Dependency graph shows backend tasks before frontend tasks that depend on them
- [ ] Each task has testable acceptance criteria
- [ ] Shared component reuse is explicit (WaveformCanvas, useTrackAnalysis — used, not rebuilt)
- [ ] Session summary written per template
- [ ] Zero code changes

## Dependencies
- Requires completion of: FE-Live-Deck-Monitor Designer (COMPLETE)
- Blocks: All Developer tasks for FE-Live-Deck-Monitor

## Open Questions
- none
