# Spec: Analysis Status Header Indicator

## Summary

Add a persistent status element in the TopBar showing what analysis/batch work is currently running. This gives the operator awareness before queueing new work and lays the foundation for analysis governance (priority rules, queue management, conflict prevention).

Route: N/A (global header element, visible on every page)

---

## Motivation

Currently, batch analysis progress is only visible on the Library page's `StrataBatchProgress` component. If the operator navigates away or starts a new session, there's no indication that analysis is running. This leads to:

- Accidentally starting overlapping batches
- No awareness of system load before triggering new work
- No foundation for governance rules (priority, queueing, concurrency limits)

---

## User-Facing Behavior

### When idle (no analysis running)

Nothing shown in the header — no indicator visible.

### When single-track analysis is running

```
TopBar:
  [SCUE v0.1.0]    [... existing status dots ...]    [Analyzing: "Track Name" (standard) ...]
```

Small pill/badge showing track name (truncated), tier, and a subtle spinner.

### When batch analysis is running

```
TopBar:
  [SCUE v0.1.0]    [... existing status dots ...]    [Batch: 42/1067 quick  ████░░░░ 3.9%]
```

Shows completed/total count, tier, and a compact progress bar. Clicking expands a dropdown with:
- Per-track status of the currently running job
- Error count (if any)
- Cancel button
- "View in Library" link (navigates to Library page with batch panel visible)

### When analysis completes

Badge briefly shows "Complete: 1067 tracks" (green) for 10 seconds, then fades out.

### When analysis fails or is cancelled

Badge shows "Batch failed: 42/1067" or "Cancelled" (amber/red) and persists until dismissed.

---

## Component Hierarchy

```
TopBar.tsx (existing)
  +-- AnalysisStatusBadge (NEW)
        +-- BatchProgressMini (inline pill, always visible when active)
        +-- BatchProgressDropdown (expanded on click)
              +-- current job detail
              +-- error summary
              +-- cancel / dismiss actions
```

---

## Data Flow

### Current: Polling only

```
Frontend polls GET /api/strata/batch/{id} every 1500ms
  -> useStrataBatchStatus() hook
  -> StrataBatchProgress component (Library page only)
```

### Proposed: WebSocket push + global store

```
Backend: _run_strata_batch() broadcasts progress via WSManager
  -> { type: "analysis_progress", payload: AnalysisProgressPayload }

Frontend: ws.ts dispatch routes to new Zustand store
  -> useAnalysisProgressStore
  -> TopBar reads store -> renders AnalysisStatusBadge
  -> Library page also reads store (replaces polling)
```

### WebSocket Message

```typescript
// New WS message type
interface WSAnalysisProgress {
  type: "analysis_progress";
  payload: {
    kind: "batch" | "single";
    batch_id?: string;
    job_id?: string;
    status: "running" | "complete" | "failed" | "cancelled";
    tier: string;
    completed: number;
    failed: number;
    total: number;
    current_track?: {
      fingerprint: string;
      title: string;
      step: number;
      step_name: string;
      total_steps: number;
    };
  };
}
```

### Backend Broadcast Points

In `_run_strata_batch()` and `_run_strata_analysis()`:
- On batch start
- After each job completes (or fails)
- On batch complete/cancel

Requires passing `WSManager` reference to strata API init (same pattern as `init_local_library_api`).

---

## Zustand Store

```typescript
// frontend/src/stores/analysisProgressStore.ts
interface AnalysisProgressState {
  // Active work
  activeBatch: AnalysisProgressPayload | null;
  activeJob: AnalysisProgressPayload | null;

  // Completion toast (auto-dismiss after 10s)
  completionMessage: string | null;

  // Actions (called from ws.ts dispatch)
  setProgress: (payload: AnalysisProgressPayload) => void;
  dismiss: () => void;
}
```

---

## Governance Foundation (Phase 2)

This spec lays the groundwork for future governance rules:

1. **Queue awareness** — before starting a new batch, check `activeBatch`. Show confirmation: "A batch is already running (42/1067). Queue this request?"
2. **Priority** — single-track requests could preempt batch work (pause current batch job, run single, resume)
3. **Concurrency limits** — backend could reject new batches while one is active, returning the active batch ID for the frontend to show

These are not part of this spec but the store and WS infrastructure enable them.

---

## Implementation Tasks

1. Backend: wire `WSManager` into `init_strata_api()` and broadcast from `_run_strata_batch()`
2. Add `"analysis_progress"` to `WSMessage` union type and `ws.ts` dispatch
3. Create `analysisProgressStore.ts` Zustand store
4. Create `AnalysisStatusBadge` component
5. Mount in `TopBar.tsx`
6. Library page: optionally replace polling with WS store data

---

## Key Files

| What | Where |
|------|-------|
| TopBar component | `frontend/src/components/layout/TopBar.tsx` |
| WS types | `frontend/src/types/ws.ts` |
| WS dispatch | `frontend/src/api/ws.ts` |
| Existing batch progress | `frontend/src/components/strata/TierAnalysisStatus.tsx` |
| Existing batch polling | `frontend/src/api/strata.ts` |
| Backend batch runner | `scue/api/strata.py` — `_run_strata_batch()` |
| Backend WS manager | `scue/api/ws_manager.py` |
| Backend init wiring | `scue/main.py` |

---

## Acceptance Criteria

- [ ] Header shows nothing when no analysis is running
- [ ] Header shows progress badge during batch analysis (count + progress bar)
- [ ] Header shows track name during single-track analysis
- [ ] Badge updates in real-time via WebSocket (no polling)
- [ ] Clicking badge expands dropdown with detail + cancel
- [ ] Badge shows completion state briefly, then auto-dismisses
- [ ] Navigating between pages does not lose analysis status
- [ ] Starting the app while a batch is in progress picks up the status
