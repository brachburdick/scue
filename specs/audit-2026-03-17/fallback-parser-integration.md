# Task Spec: Wire Fallback Parser into BridgeManager

**Source:** Audit 2026-03-17, Domain A (Layer 0)
**Priority:** Gap (M0 scope, not yet complete)
**Blocked by:** Nothing
**Touches:** `scue/bridge/manager.py`, `scue/bridge/fallback.py`
**Layer boundary:** Single layer (L0) — safe to proceed without cross-layer review

## Problem

`BridgeManager` defines a `fallback` state in its state machine but never transitions into it. When the bridge subprocess is unavailable (no JRE, no JAR, or repeated crashes), the manager stops at `no_jre`/`no_jar`/`crashed` rather than falling through to the UDP fallback parser.

`FallbackParser` in `fallback.py` (377 lines) is fully implemented and emits `BridgeMessage` objects with the same interface as the real bridge — but it's never instantiated by the manager.

MILESTONES.md lists `fallback.py` as an M0 deliverable (checked off), but integration is incomplete.

## Desired Behavior

1. When `BridgeManager` detects `no_jre` or `no_jar`, it should:
   - Log a warning: "Bridge unavailable ({reason}), starting UDP fallback parser (degraded mode)"
   - Transition to `fallback` state
   - Instantiate `FallbackParser` and call `await parser.start()`
   - Route `FallbackParser.on_message` callback through the same adapter pipeline
   - The adapter + external callback should see `BridgeMessage` objects from fallback, transparently

2. When bridge becomes available again (e.g., JAR placed at expected path), a manual `restart()` call should:
   - Stop fallback parser
   - Attempt normal bridge startup
   - Fall back again if bridge startup fails

3. After N consecutive crash-restart cycles (configurable, suggest 3), the manager should:
   - Stop attempting bridge restart
   - Fall through to fallback mode
   - Log: "Bridge crashed {N} times, switching to fallback mode"

## Degraded Mode Capabilities (document clearly)

Fallback **provides:** device_found, player_status, beat events (BPM, beat_within_bar, pitch, play state)
Fallback **does NOT provide:** track_metadata, beat_grid, waveform_detail, phrase_analysis, cue_points

This means Layer 1B can track BPM and beat position but cannot enrich tracks or build full cursors. This is acceptable for basic beat-reactive effects.

## Implementation Notes

- `FallbackParser` already emits `BridgeMessage` objects — no adapter changes needed
- `FallbackParser.on_message` callback signature matches manager's expectation
- Network interface must be passed to `FallbackParser` for `pioneer_interfaces()` filtering
- `to_status_dict()` should include `mode: "fallback"` or similar to let the frontend show degraded state
- Frontend `StatusBanner` already handles `fallback` status (yellow badge)

## Test Plan

- [ ] Unit: Manager transitions to `fallback` state when `no_jre`
- [ ] Unit: Manager transitions to `fallback` state when `no_jar`
- [ ] Unit: Manager transitions to `fallback` after N crash cycles
- [ ] Unit: Fallback parser messages flow through adapter to callbacks
- [ ] Unit: `restart()` from fallback state stops parser, attempts bridge
- [ ] Unit: `to_status_dict()` reflects fallback mode
- [ ] Integration: FallbackParser standalone tests (currently missing — add)

## Files to Modify

| File | Change |
|------|--------|
| `scue/bridge/manager.py` | Add fallback transition logic, instantiate FallbackParser |
| `scue/bridge/fallback.py` | No changes expected (already complete) |
| `tests/test_bridge/test_manager.py` | Add fallback state transition tests |
| `tests/test_bridge/test_fallback.py` | NEW — standalone fallback parser tests |
| `docs/MILESTONES.md` | Update M0 to note integration completion |

## Acceptance Criteria

- Manager never sits in `no_jre`/`no_jar` if fallback can run
- Fallback messages are indistinguishable from bridge messages to Layer 1
- Frontend shows "Fallback (degraded)" status with yellow indicator
- Graceful shutdown of fallback on manager.stop()
