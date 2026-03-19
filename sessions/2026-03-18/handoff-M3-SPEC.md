# Handoff Packet: TASK-M3-SPEC

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/ARCHITECT.md` (if it exists; otherwise use COMMON_RULES context)

## Objective
Produce a complete feature spec and task breakdown for Milestone 3 — Cue Stream (Layer 2), covering the transformation of `DeckMix` (Layer 1 output) into a `CueEvent` stream (Layer 2 output) for section-level cues only.

## Role
Architect

## Scope Boundary
- Files this agent MAY create:
  - `specs/feat-M3-cue-stream/spec.md`
  - `specs/feat-M3-cue-stream/tasks.md`
- Files this agent MAY read (not modify):
  - `docs/ARCHITECTURE.md`
  - `docs/CONTRACTS.md`
  - `docs/DECISIONS.md`
  - `docs/MILESTONES.md`
  - `LEARNINGS.md`
  - `scue/layer1/models.py` (read — understand DeckMix, TrackCursor, SectionInfo output)
  - `scue/layer1/cursor.py` (read — understand cursor construction)
  - `scue/layer1/tracking.py` (read — understand PlaybackTracker output)
  - `config/` (read — understand existing YAML config patterns)
- Files this agent must NOT touch:
  - Any existing source code (no modifications)
  - `docs/CONTRACTS.md` (propose changes in the spec; Orchestrator coordinates the update)
  - Any frontend files

## Context Files
- `docs/ARCHITECTURE.md` — Layer 2 description, cue taxonomy, CueEvent structure
- `docs/CONTRACTS.md` — Layer 1→2 interface (DeckMix) and Layer 2→3 interface (CueEvent)
- `docs/DECISIONS.md` — existing ADRs that constrain Layer 2 design
- `docs/MILESTONES.md` — M3 milestone entry (currently just a title)
- `LEARNINGS.md` — project pitfalls

## Background
Layer 1 is complete. It outputs `DeckMix` (list of `WeightedCursor` objects, each containing a `TrackCursor` with section info, beat position, playback state, and features). Layer 2 must transform this into a `CueEvent` stream.

**M3 scope is section-level cues only.** This means:
- Section boundary cues (entering/leaving a section)
- Section type cues (drop, build, breakdown, etc. — different cue behavior per section type)
- Section progress cues (approaching end of section, halfway through, etc.)
- Energy trajectory cues (if sections have different energy levels)

**NOT in M3 scope:**
- Beat-level cues (M8 — Full Cue Vocabulary)
- Event detection cues (M7 — Event Detection)
- Multi-deck mixing cues (can be noted in spec as future consideration)

## Deliverables

### 1. `specs/feat-M3-cue-stream/spec.md`
Using the template at `templates/spec.md`, produce:
- **Overview:** What Layer 2 does and why
- **Input contract:** DeckMix structure (reference CONTRACTS.md, don't copy)
- **Output contract:** CueEvent stream — define the section-level cue types, their payloads, intensity mapping, priority rules
- **Processing model:** How DeckMix is transformed into CueEvents. Is this a polling loop? Event-driven? What's the tick rate?
- **Cue taxonomy (M3 subset):** Define exactly which cue types exist for section-level cues, their `type` strings, intensity curves, and duration rules
- **Configuration:** What's configurable via YAML? (cue intensity curves, section-type-to-cue mappings, timing thresholds)
- **State management:** What state does Layer 2 maintain between ticks? (current section per deck, pending cues, cooldowns)
- **Error handling:** What happens when DeckMix is empty, has stale data, or cursor has no section info?
- **Testing strategy:** How to test cue generation without live hardware (mock DeckMix inputs)

### 2. `specs/feat-M3-cue-stream/tasks.md`
Using the template at `templates/tasks.md`, break down implementation into atomized tasks:
- Each task must pass the atomization test (single-layer, <30min, independently testable, fully specified)
- Include: Layer 2 models, cue generator, configuration loader, test fixtures, API exposure (if any)
- Identify which tasks can run in parallel

## Constraints
- Layer 2 MUST NOT import from Layer 1 except through the defined DeckMix contract (see CONTRACTS.md)
- Layer 2 output MUST conform to the CueEvent contract in CONTRACTS.md (propose amendments if needed, flagged as `[CONTRACT CHANGE]`)
- All configuration must be YAML files in `config/` — no hardcoded values
- The spec must account for multi-deck scenarios (2-4 decks) even if M3 only implements single-deck-at-a-time
- If you need to propose changes to CONTRACTS.md, flag them clearly as `[CONTRACT CHANGE]: description` — do not edit the file yourself

## Acceptance Criteria
- [ ] `specs/feat-M3-cue-stream/spec.md` written with all sections listed above
- [ ] `specs/feat-M3-cue-stream/tasks.md` written with atomized tasks and dependency graph
- [ ] Cue taxonomy for section-level cues is complete (every section type maps to defined cue behavior)
- [ ] Processing model is defined (tick-based vs event-driven, with justification)
- [ ] Configuration schema is specified (what YAML keys, what defaults)
- [ ] Contract changes (if any) are flagged with `[CONTRACT CHANGE]`
- [ ] Testing strategy includes mock DeckMix fixtures
- [ ] All design decisions documented with rationale and rejected alternatives
- [ ] Session summary written to `sessions/2026-03-18/architect-m3-spec.md`

## Dependencies
- Requires completion of: M0 (COMPLETE), M2 (COMPLETE) — Layer 1 output types exist
- Blocks: M3 implementation tasks

## Open Questions
None — proceed with the spec. If you encounter ambiguities about cue behavior or intensity mapping, make a reasonable default and flag `[DECISION OPPORTUNITY]` for Brach.
