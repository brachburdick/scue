# Audit Findings Summary — 2026-03-17

**Scope:** M0–M2 + Frontend (all completed milestones)
**Method:** Full source code read, cross-referenced against ARCHITECTURE.md, CONTRACTS.md, DECISIONS.md, MILESTONES.md, STATUS_2026-03-17.md, LEARNINGS.md, and per-layer bug logs.

---

## Overall Assessment

The codebase is in strong shape. Layer boundaries are clean, contract types match exactly between docs and code, and test coverage is solid where it matters (Layer 0: 1,417 lines, Layer 1: 2,655 lines). The frontend is strictly typed with zero `any` usage and proper store isolation.

---

## Issues Found

### Blockers

| # | Issue | Domain | Spec |
|---|-------|--------|------|
| 1 | Traffic detected but device never discovered | L0 | `specs/audit-2026-03-17/traffic-no-device-blocker.md` |

### Gaps (incomplete deliverables)

| # | Issue | Domain | Spec |
|---|-------|--------|------|
| 2 | Fallback parser implemented but not wired into BridgeManager | L0 | `specs/audit-2026-03-17/fallback-parser-integration.md` |
| 3 | No API-level tests | API | `specs/audit-2026-03-17/api-test-coverage.md` |

### Hygiene (rule violations, dead code)

| # | Issue | Domain | Spec |
|---|-------|--------|------|
| 4 | Hardcoded values violate "config is YAML" rule | API/Config | `specs/audit-2026-03-17/yaml-config-consolidation.md` |
| 5 | `config/usb.yaml` exists but is never loaded | Config | (covered in #4 spec) |

### Doc Drift

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| 6 | "React 18" → code is React 19.2.4 | CLAUDE.md, ARCHITECTURE.md (×2), STATUS_2026-03-17.md | Update to "React 19" |
| 7 | MILESTONES.md missing FE-BLT (Bridge Page) | MILESTONES.md | Add completed milestone entry |
| 8 | MILESTONES.md FE-2 still in backlog but partially done | MILESTONES.md | Update status |
| 9 | M0 marked complete but fallback not integrated | MILESTONES.md | Add unchecked item or create sub-milestone |
| 10 | `network/CLAUDE.md` was a stub | `scue/network/CLAUDE.md` | DONE — written during this audit |
| 11 | `scue/api/CLAUDE.md` is a stub | `scue/api/CLAUDE.md` | Future — write during API test work |

### Downstream Implications (no action now, logged for awareness)

| # | Note |
|---|------|
| 12 | WebSocket protocol only has 2 message types (`bridge_status`, `pioneer_status`). Will need `track_cursor`, `beat_event`, etc. for M3+ live features. Consider versioning the WS protocol. |
| 13 | Watchdog timing chain (5s backend threshold, 2s poll interval, 8s frontend grace) is spread across 3 files with no coordination. Consolidating to config (spec #4) will help, but the values themselves may need tuning once the traffic blocker (#1) is resolved. |
| 14 | EDM flow model is energy-based. If genre scope expands beyond EDM, the classification approach will need rethinking. |

---

## What's Clean (no action needed)

- **Layer boundaries:** Zero cross-layer import violations across entire codebase
- **CONTRACTS.md types:** Exact match between docs and code (BridgeMessage, TrackCursor, PlayerState, all payload types)
- **Layer 1:** Exemplary — 3,441 lines, 2,655 test lines, zero bugs logged, zero TODOs
- **Frontend stores:** Independent silos, no cross-imports
- **Frontend types:** All FE/BE boundary types in `src/types/`, strict mode, no `any`
- **Enrichment pipeline:** Deep copy, versioned, never overwrites original — correct
- **Divergence logging:** Full audit trail in SQLite — correct
- **Frontend startup gating:** Consistent `enabled: !isStartingUp` pattern across all queries

---

## Deliverables Produced

| Deliverable | Path |
|-------------|------|
| Fallback parser integration spec | `specs/audit-2026-03-17/fallback-parser-integration.md` |
| Traffic detection blocker spec | `specs/audit-2026-03-17/traffic-no-device-blocker.md` |
| YAML config consolidation spec | `specs/audit-2026-03-17/yaml-config-consolidation.md` |
| API test coverage spec | `specs/audit-2026-03-17/api-test-coverage.md` |
| Network module CLAUDE.md | `scue/network/CLAUDE.md` |
| This findings summary | `specs/audit-2026-03-17/findings-summary.md` |
| Doc fix proposals | (see below — pending your approval) |
