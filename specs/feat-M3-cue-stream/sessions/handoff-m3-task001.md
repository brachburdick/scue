# Handoff Packet: M3-TASK-001

---
status: ON HOLD — M3 paused pending data-flow research and M0-M2 feature scoping
project_root: /Users/brach/Documents/THE_FACTORY/DjTools/scue
revision_of: none
supersedes: none
superseded_by: none
---

## Dispatch
- Mode: DIRECT DISPATCH
- Output path: `specs/feat-M3-cue-stream/sessions/session-001-developer-task001.md`
- Parallel wave: Wave 1 (solo)

## Objective
Define the Layer 2 data models (`CueEvent`, `MusicalContext`, `DeckState`) as Python dataclasses, and update `docs/interfaces.md` to add the `deck_number: int` field to the CueEvent contract.

## Role
Developer

## Working Directory
- Run from: `/Users/brach/Documents/THE_FACTORY/DjTools/scue`
- Related feature/milestone: M3 Cue Stream (Layer 2)

## Scope Boundary
- Files this agent MAY read/modify:
  - `scue/layer2/models.py` (create)
  - `scue/layer2/__init__.py` (modify — add public exports)
  - `docs/interfaces.md` (modify — add `deck_number: int` to CueEvent)
- Files this agent must NOT touch:
  - Any file in `scue/layer1/`, `scue/layer0/`, `scue/layer3/`, `scue/layer4/`
  - Any file in `frontend/`
  - `scue/layer2/generators/` (out of scope for this task)
  - `scue/layer2/CLAUDE.md` (that's TASK-009)
  - `config/` files

## Context Files
- `AGENT_BOOTSTRAP.md`
- `preambles/COMMON_RULES.md`
- `preambles/DEVELOPER.md`
- `docs/interfaces.md` — canonical contract reference (CueEvent, MusicalContext definitions in "Layer 2 -> Layer 3" section)
- `specs/feat-M3-cue-stream/spec.md` — full spec including DeckState definition, CueEvent.deck_number proposal, and CueConfig dataclasses
- `scue/layer1/models.py` — reference pattern for dataclass style (import nothing from here, just match the style)
- `LEARNINGS.md`

## Interface Contracts
- `docs/interfaces.md` — "Layer 2 -> Layer 3: CueEvent stream" section
- **CONTRACT CHANGE:** Add `deck_number: int` field to `CueEvent` in `docs/interfaces.md`. This is an additive, non-breaking change. Place it after the `priority` field. Add a comment: `# player_number from the originating deck (1-4)`.

## Required Output
- Write: `specs/feat-M3-cue-stream/sessions/session-001-developer-task001.md`
- If you supersede an existing artifact, mark it `SUPERSEDED` before session end.
- If you discover backlog-worthy out-of-scope improvements, capture them in `## Follow-Up Items` of the session summary.

## Constraints
- Layer 2 MUST NOT import from `scue.layer1` except the contract types listed in TR-05 of the spec. For this task, no layer1 imports are needed — the models are standalone.
- All fields must have type hints.
- Use `@dataclass` (not Pydantic, not TypedDict).
- Use `field(default_factory=list)` for mutable defaults (e.g., `energy_history` in `DeckState`).
- Follow the existing dataclass style in `scue/layer1/models.py` (read it for reference).

## Acceptance Criteria
- [ ] `scue/layer2/models.py` exists and contains `CueEvent`, `MusicalContext`, `DeckState` dataclasses
- [ ] `CueEvent` matches the contract in `docs/interfaces.md` **plus** `deck_number: int`
- [ ] `MusicalContext` matches the contract in `docs/interfaces.md`
- [ ] `DeckState` matches the spec definition (fields: `player_number`, `current_section_label`, `current_section_start`, `last_bar_in_section`, `last_downbeat_seen`, `anticipation_fired_for`, `energy_history`, `cue_counter`)
- [ ] All fields have type hints
- [ ] `scue/layer2/__init__.py` exports `CueEvent`, `MusicalContext`, `DeckState`
- [ ] `docs/interfaces.md` updated: `deck_number: int` added to CueEvent class definition with comment
- [ ] Module imports successfully: `from scue.layer2.models import CueEvent, MusicalContext, DeckState`
- [ ] All pre-existing tests pass: `cd /Users/brach/Documents/THE_FACTORY/DjTools/scue && .venv/bin/python -m pytest tests/ -x -q`

## Dependencies
- Requires completion of: none
- Blocks: M3-TASK-002, M3-TASK-003

## Open Questions
- none
