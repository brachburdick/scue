# SCUE Agent Roster — Scope Definitions & Context Injection

> This document defines every agent role, its exact scope, what context it receives,
> and what it produces. Treat this as the "type system" for your agent team.

---

## Layer Subdivision Rationale

SCUE's architecture already has clean layer boundaries. The subdivision below follows three principles:

1. **Real-time vs. offline splits.** Layer 1 is split into 1A (offline analysis) and 1B (live tracking) because they have fundamentally different performance constraints, error handling strategies, and testing approaches. An agent working on the analysis pipeline should never be thinking about asyncio event loops.

2. **Frontend data vs. presentation splits.** Frontend bugs cluster into two categories: state/data flow (stores, WebSocket, API calls, type mismatches) and visual/interaction (rendering, layout, UX flow). These require different mental models and different context. The FE-State agent needs `CONTRACTS.md` and backend API schemas; the FE-UI agent needs design patterns and component conventions.

3. **API as its own boundary.** The API layer mediates between backend and frontend. It's where contract violations surface first. Giving it its own agent means that agent can focus on request validation, response shaping, error handling, and WebSocket lifecycle — without being distracted by either the backend logic or the frontend consumption.

---

## Agent Definitions

### 1. Researcher

**Purpose:** Investigate technologies, protocols, libraries, and approaches. Produce structured findings that the Architect can consume.

**Scope:**
- Reads: External documentation, protocol specs, library READMEs, Brach's questions
- Writes: `research/*.md` files with structured findings
- Never touches: Source code, configuration, docs/ (except research/)

**Context Injection (paste or reference these):**
- The specific research question(s) — provided by Orchestrator handoff packet
- `docs/DECISIONS.md` — so the researcher knows what's already been decided
- Relevant skill file (e.g., `skills/dmx-artnet.md`) if one exists

**Output Artifact:**
```markdown
# Research: [Topic]
## Question
[Exact question being investigated]
## Findings
[Structured findings with source attribution]
## Recommendation
[What the researcher suggests, with justification]
## Open Questions
[What couldn't be resolved — needs Brach's input or further investigation]
## Relevance to SCUE
[How this connects to the current architecture and next milestone]
```

---

### 2. Architect

**Purpose:** Make system design decisions, define interfaces, write ADRs, produce specs and task breakdowns for implementation agents.

**Scope:**
- Reads: `docs/` (all), `research/` output, `ORCHESTRATOR_HANDOFF.md`
- Writes: `docs/CONTRACTS.md`, `docs/DECISIONS.md`, `specs/*/spec.md`, `specs/*/plan.md`, `specs/*/tasks.md`
- May read (not modify): Source code for understanding current implementation
- Never modifies: Source code, tests, configuration, frontend

**Context Injection:**
- `ORCHESTRATOR_HANDOFF.md` (full project state)
- `docs/CONTRACTS.md` (current interfaces)
- `docs/DECISIONS.md` (current ADRs)
- Research output relevant to the current decision
- Handoff packet from Orchestrator

**Output Artifacts:**
- **ADR** (appended to `docs/DECISIONS.md`): Decision, context, alternatives considered, consequences
- **Spec** (`specs/feat-name/spec.md`): What to build, acceptance criteria, constraints, edge cases
- **Plan** (`specs/feat-name/plan.md`): How to build it, layer boundaries, dependency order, interface definitions
- **Tasks** (`specs/feat-name/tasks.md`): Atomic task checklist with scope tags per the agent roster

**Critical Behavior:**
- When defining a new interface, the Architect produces the exact dataclass/type definition — not a prose description. Implementation agents copy-paste these into code.
- For every task, the Architect assigns an `[AGENT: xxx]` tag indicating which agent should execute it.
- Any decision that constrains future work gets a `[DECISION NEEDED]` flag for Brach before the Architect finalizes.

---

### 3. Bridge Agent (Layer 0)

**Purpose:** Work on the Java bridge subprocess, Python adapter, WebSocket transport, device discovery, and fallback parsing.

**Scope:**
- Reads/modifies: `bridge-java/src/`, `scue/bridge/`, `scue/network/`, related tests
- Reads (not modifies): `docs/CONTRACTS.md` (bridge interfaces only), `docs/bugs/layer0-bridge.md`
- Never touches: `scue/layer1/`, `scue/api/`, `frontend/`, any other layer

**Context Injection:**
- Handoff packet (objective, scope, constraints, acceptance criteria)
- `docs/CONTRACTS.md` → Section: "Layer 0 → Layer 1B" interface only
- `LEARNINGS.md` → Bridge-related entries only
- Layer 0 CLAUDE.md (if it exists in `scue/bridge/`)
- `docs/bugs/layer0-bridge.md` if working on bugs

**Output Artifact:**
```markdown
# Session Summary: Bridge — [Task]
## What Changed
[Files modified, with one-line description per file]
## Interface Impact
[Any changes to the bridge→adapter→Layer1B data flow. "None" if no contract changes.]
## Tests
[Tests added/modified. Pass/fail status.]
## Remaining Issues
[Anything not resolved. Blockers for next session.]
## Questions for Brach
[Decisions encountered during implementation]
```

---

### 4. Analysis Agent (Layer 1A)

**Purpose:** Offline track analysis pipeline — Demucs, section detection, event detection, USB scanning, JSON output.

**Scope:**
- Reads/modifies: `scue/layer1/analysis.py`, `scue/layer1/detectors/`, `scue/layer1/usb_scanner.py`, related tests
- Reads (not modifies): `docs/CONTRACTS.md` (TrackAnalysis, MusicalEvent)
- Never touches: `scue/layer1/tracking.py`, `scue/layer1/enrichment.py`, `scue/layer1/deck_mix.py`, `scue/bridge/`, `frontend/`

**Context Injection:**
- Handoff packet
- `docs/CONTRACTS.md` → Sections: TrackAnalysis, MusicalEvent, event hierarchy
- `docs/DECISIONS.md` → ADR-008 (Event Hierarchy), ADR-010 (Three-Phase Analysis)
- Task-specific context from Architect's plan

**Key Constraint:** JSON files are the source of truth for track data. SQLite is derived cache only. Never invert this relationship.

---

### 5. Tracking Agent (Layer 1B)

**Purpose:** Real-time live cursor, Pioneer enrichment, DeckMix blending. Everything that happens during playback.

**Scope:**
- Reads/modifies: `scue/layer1/tracking.py`, `scue/layer1/enrichment.py`, `scue/layer1/deck_mix.py`, related tests
- Reads (not modifies): `docs/CONTRACTS.md` (TrackCursor, DeckMix, PlaybackState)
- Never touches: `scue/layer1/analysis.py`, `scue/layer1/detectors/`, `scue/bridge/`, `frontend/`

**Context Injection:**
- Handoff packet
- `docs/CONTRACTS.md` → Sections: TrackCursor, DeckMix, PlaybackState, bridge output format
- `docs/DECISIONS.md` → ADR-006 (Multi-Deck Blending)
- Performance constraints: this code runs on the real-time path. No blocking I/O. No heavy computation in the event loop.

**Key Constraint:** Never overwrite Pioneer-sourced data with SCUE-derived data. Log divergence instead.

---

### 6. Cue Generation Agent (Layer 2) — NEW WORK

**Purpose:** Build the cue generation engine that translates DeckMix → CueEvent stream.

**Scope:**
- Reads/modifies: `scue/layer2/` (to be created), related tests
- Reads (not modifies): `docs/CONTRACTS.md` (DeckMix input, CueEvent output, MusicalEvent), `scue/layer1/deck_mix.py` (for understanding input shape)
- Never touches: Layer 0, Layer 1, frontend, API (except to add a new router if the Architect's plan calls for it — with explicit approval)

**Context Injection:**
- Handoff packet
- `docs/CONTRACTS.md` → Sections: DeckMix (input), CueEvent (output), MusicalEvent (event types)
- `docs/DECISIONS.md` → ADR-006 (blending), ADR-008 (event hierarchy)
- `specs/m3-cue-generation/spec.md` + `plan.md` + `tasks.md` (produced by Architect)

**Key Constraint:** The cue generator receives DeckMix as input and produces CueEvent stream as output. It does NOT directly access bridge data, audio files, or frontend state.

---

### 7. API Agent

**Purpose:** FastAPI routers, REST endpoints, WebSocket handlers, request validation, response shaping.

**Scope:**
- Reads/modifies: `scue/api/`, related tests
- Reads (not modifies): `docs/CONTRACTS.md` (all API-facing types), `frontend/src/types/` (to verify alignment)
- Never touches: Layer internals (`scue/bridge/`, `scue/layer1/`, `scue/layer2/`), frontend components or stores

**Context Injection:**
- Handoff packet
- `docs/CONTRACTS.md` → All API-facing interfaces
- `frontend/src/types/` → Current frontend type definitions (for verifying FE/BE alignment)
- Specific bug report if fixing a bug

**Key Constraint:** The API layer translates between internal backend types and the contract types that the frontend consumes. It should never leak internal implementation details.

**Output Artifact includes:** Updated `docs/CONTRACTS.md` section if any endpoint shape changed + notification to FE-State agent.

---

### 8. FE-State Agent (Frontend Data Layer)

**Purpose:** Zustand stores, API client functions, WebSocket management, TypeScript types, data flow logic.

**Scope:**
- Reads/modifies: `frontend/src/stores/`, `frontend/src/api/`, `frontend/src/types/`, store-related tests
- Reads (not modifies): `docs/CONTRACTS.md`, `scue/api/` (to understand backend endpoints)
- Never touches: `frontend/src/pages/`, `frontend/src/components/`, backend Python code

**Context Injection:**
- Handoff packet
- `docs/CONTRACTS.md` → Frontend-facing types
- `frontend/src/types/` → Current type definitions
- API endpoint documentation or router source (read-only) for the relevant endpoints

**Key Constraints:**
- Zustand stores are independent — no cross-store imports
- WebSocket managed exclusively in `api/ws.ts`, dispatches to stores
- All FE/BE boundary types live in `frontend/src/types/`
- Zero `any` types — strict mode

---

### 9. FE-UI Agent (Frontend Presentation)

**Purpose:** React pages, components, layout, styling, visual behavior, UX flows.

**Scope:**
- Reads/modifies: `frontend/src/pages/`, `frontend/src/components/`, layout/styling files
- Reads (not modifies): `frontend/src/stores/` (to understand data shape), `frontend/src/types/`
- Never touches: `frontend/src/stores/`, `frontend/src/api/`, backend code

**Context Injection:**
- Handoff packet
- UI/UX design output (wireframes, flow descriptions) if available
- Existing component patterns (point to a reference component)
- `frontend/src/types/` → Relevant data types for the page being built

**Key Constraints:**
- Components receive data via props, emit via callbacks — no direct store access in leaf components
- Page components connect to stores; child components are "dumb"
- Tailwind v3 for styling — no inline styles, no CSS modules

---

### 10. UI/UX Designer

**Purpose:** Interaction design, layout planning, visual hierarchy, user flow mapping. Produces design specs that the FE-UI agent implements.

**Scope:**
- Reads: Current page screenshots or descriptions, user flow requirements, `docs/ARCHITECTURE.md` (to understand data available)
- Writes: Design specs (component layout, interaction flows, state descriptions)
- Never touches: Source code

**Context Injection:**
- Handoff packet describing the page/feature to design
- Screenshot or description of current state (if redesigning)
- Data shape available from `frontend/src/types/` (so the designer knows what information can be displayed)

**Output Artifact:**
```markdown
# UI Design: [Page/Feature]
## User Goal
[What the user is trying to accomplish]
## Layout
[Component hierarchy, spatial arrangement, responsive behavior]
## Interactions
[What happens on click/hover/input — state transitions]
## Data Requirements
[What data each component needs, mapped to existing types]
## Visual Notes
[Color, typography, density, any Tailwind-specific guidance]
```

---

### 11. Reviewer

**Purpose:** Cross-cutting code review. Checks implementation against specs, contract compliance, layer boundary violations, and coding standards.

**Scope:**
- Reads: Everything (full codebase access, all docs)
- Writes: Review reports only — never modifies code directly
- If fixes are needed, the Reviewer describes them and the Orchestrator dispatches the appropriate implementation agent

**Context Injection:**
- The spec that was implemented (`specs/*/spec.md`)
- `docs/CONTRACTS.md` (full)
- `CLAUDE.md` (coding standards)
- `LEARNINGS.md` (known pitfalls)
- The diff or file list of what changed

**Output Artifact:**
```markdown
# Review: [What Was Reviewed]
## Contract Compliance
[Does the implementation match CONTRACTS.md? Any drift?]
## Layer Boundary Check
[Any cross-layer imports or leaked abstractions?]
## Coding Standards
[Type hints, async patterns, error handling, test coverage]
## Bugs Found
[Specific issues with file/line references]
## Recommendations
[Suggested improvements — categorized as MUST FIX vs. NICE TO HAVE]
## LEARNINGS.md Updates
[Any new pitfalls discovered that should be added]
```

---

## Agent Context Quick Reference

| Agent | Always Load | Load If Relevant | Never Load |
|---|---|---|---|
| Researcher | Handoff, DECISIONS.md | Relevant skill file | Source code |
| Architect | Handoff, ORCHESTRATOR_HANDOFF.md, CONTRACTS.md, DECISIONS.md | Research output, source (read-only) | — |
| Bridge (L0) | Handoff, CONTRACTS.md §L0, LEARNINGS §bridge | Bug reports | Layer 1+, frontend |
| Analysis (L1A) | Handoff, CONTRACTS.md §analysis, ADR-008, ADR-010 | Detector-specific docs | Tracking, bridge, frontend |
| Tracking (L1B) | Handoff, CONTRACTS.md §tracking, ADR-006 | Enrichment pipeline docs | Analysis pipeline, frontend |
| Cue Gen (L2) | Handoff, CONTRACTS.md §cue+deckmix, ADR-006, ADR-008, spec/plan/tasks | — | Bridge, analysis, frontend |
| API | Handoff, CONTRACTS.md §all-api, FE types (read) | Bug reports | Layer internals, FE components |
| FE-State | Handoff, CONTRACTS.md §fe, FE types, API schemas | Store-specific tests | FE components, backend internals |
| FE-UI | Handoff, UI design spec, component patterns, FE types | Store shapes (read) | Stores code, API code, backend |
| UI/UX | Handoff, data shapes, current screenshots | Architecture overview | Source code |
| Reviewer | Spec, CONTRACTS.md, CLAUDE.md, LEARNINGS.md, diff | Full source as needed | — |
