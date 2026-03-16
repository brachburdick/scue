# Architectural Decision Records (ADRs)

## ADR-001: Pioneer beatgrid as source of truth over librosa
Date: 2025-03
Context: librosa beat tracking drifts on tempo-variable tracks; Pioneer grids are hand-verified by the DJ in rekordbox and are more reliable.
Decision: The librosa-derived beatgrid from offline analysis serves as the working reference during analysis and as a fallback when Pioneer data is unavailable. When a track is first loaded on Pioneer hardware, the Pioneer enrichment pass replaces the librosa beatgrid with the Pioneer beatgrid. SCUE's original analysis is kept (versioned) — the Pioneer-enriched version is stored alongside it, not in place of it.
Consequences: Layer 1B must trigger the enrichment pass on first track load. TrackCursor reads from the enriched analysis if available, falling back to the raw offline analysis. All divergences between SCUE and Pioneer data must be logged via DivergenceRecord.

## ADR-002: Fixed-rate main loop (40Hz) with beat injection
Date: 2025-03
Context: Beat-synchronized ticks (variable rate depending on BPM) complicate timer logic and produce variable-rate output. Fixed-rate is simpler and gives smoother continuous effects.
Decision: The real-time processing loop ticks at 40Hz (every 25ms). Beat events from the TrackCursor are injected into the cue engine as discrete events when they occur. Effects that need beat sync reference the beat grid via the cursor, not the tick rate.
Consequences: Layer 2 cue generators receive both tick callbacks and beat event callbacks.

## ADR-003: YAML for all configuration; no hardcoded effect/fixture values
Date: 2025-03
Context: Effect definitions, fixture profiles, routing tables, and palettes need to be user-editable without code changes.
Decision: All configuration lives in `config/`. Effect definitions, fixture profiles, venue layouts, routing tables, and palettes are YAML files. Python code implements the runtime machinery; YAML files define the data. Adding a new effect type, fixture, or routing rule should not require touching Python.
Consequences: All config-loading code must handle missing or malformed YAML gracefully. Ship defaults for all config categories.

## ADR-004: Direct Pro DJ Link UDP, no beat-link-trigger
Date: 2025-03
Context: Initially planned to use beat-link-trigger as middleware (Java app that speaks Pro DJ Link and can re-broadcast via OSC). But this requires the DJ to install and configure beat-link-trigger, set up OSC expressions, and keep it running alongside SCUE. The DJ never configured the OSC expressions, so no data arrived.
Decision: SCUE speaks Pro DJ Link UDP directly. Parses keepalive (port 50001) and status (port 50000) packets natively. No beat-link-trigger dependency.
Consequences: SCUE must handle Pro DJ Link protocol details (magic bytes, packet offsets, firmware variants). macOS socket quirk (IP_BOUND_IF) must be handled. See LEARNINGS.md for the broadcast reception issue.

## ADR-005: Master-deck-only cursor for Milestone 2
Date: 2025-03
Context: Fully tracking two decks simultaneously during a transition requires a cue-stream mixer, which is significant complexity. We only need one cursor for the initial demo.
Decision: The TrackCursor follows the master deck only (the deck with the MASTER flag set in Pioneer status). When the DJ blends two tracks, SCUE tracks whichever deck is designated master.
Consequences: During crossfades, SCUE may miss events from the incoming track until it becomes master. Full dual-deck support is deferred to post-Milestone 6.

## ADR-006: Layer isolation — no cross-layer imports
Date: 2025-03
Context: Preventing accidental coupling between layers.
Decision: Each layer may only import from its own package and from `docs/CONTRACTS.md`-defined shared types. Layer 2 does not import from layer1's internals. Layer 3 does not import from layer2's internals. Etc. Shared types (TrackCursor, CueEvent, FixtureOutput) are defined in their producing layer's `models.py` and imported by the consuming layer — only those types, nothing else.
Consequences: Refactoring a layer's internals cannot break another layer as long as the contract types are unchanged.
