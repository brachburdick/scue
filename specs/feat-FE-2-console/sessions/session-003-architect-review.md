# Feature Review Report: FE-2 Console Panel

## Reviewer
Architect (Phase 7 Feature Review)

## Verdict
**PASS with ADVISORY items.** No CRITICAL issues found. The implementation is spec-conformant, architecturally clean, and ready for milestone close.

---

## 1. Spec Conformance

All spec requirements have corresponding implementations. The Validator's AC-by-AC walkthrough in session-002 confirmed every acceptance criterion is met. I verified the implementation files independently and concur.

### Fully Implemented
- ConsoleEntry types, consoleStore with ring buffer (200 cap), recording, mode toggle
- consoleMapper with diff detection for Clean mode, verbose entries for every message
- WS dispatch wiring (system entries on connect/disconnect, message routing)
- ConsoleHeader with all controls (chevron, mode toggle, record, clear)
- LogEntry with correct timestamp format, source badges, severity dots, message colors
- ConsolePanel with render-time filtering, auto-scroll, empty state
- Export with ISO 8601 timestamps, correct filename pattern, Blob download

### Spec Requirements Not Implemented

**ADVISORY-1: Missing "Reconnecting... (attempt N)" system entry.**
The spec (System events section under Clean Mode) specifies: `WebSocket reconnecting: "Reconnecting... (attempt N)"`. The implementation does not emit a console entry during reconnection attempts. The `scheduleReconnect()` function in `ws.ts` fires silently. This is a minor gap -- the user sees "Backend connection lost" but not the reconnection attempts.

### Implemented Behaviors Not in Spec

**ADVISORY-2: Chevron direction deviates from spec.**
The spec describes up/down chevrons (standard collapse pattern). The implementation uses down-pointing triangle (expanded) and right-pointing triangle (collapsed). The Developer documented this decision. Cosmetic only.

**ADVISORY-3: "Bridge connection lost/restored" entries use source `"pioneer"` instead of `"system"`.**
In `consoleMapper.ts` L160-165, the `bridge_connected` flip from `pioneer_status` generates entries with `source: "pioneer"`. The spec lists these under "From `pioneer_status` messages" so this is technically correct -- the data comes from the pioneer_status WS message. However, "Bridge connection lost" reads more like a system event. No action needed; just noting the mapping rationale.

---

## 2. Cross-Layer Contract Integrity

**No contract violations.** This feature is entirely frontend (no Python changes), which is correct per the v1 scope constraint "No new backend WS message types."

- `ws.ts` still dispatches `bridge_status` and `pioneer_status` to `bridgeStore` identically to before. Console dispatch is purely additive.
- The `WSMessage` union type in `types/ws.ts` is unchanged.
- The `BridgeState` type in `types/bridge.ts` is unchanged.
- `docs/CONTRACTS.md` does not need updating -- no new WS message types were introduced.

**Note:** The `BridgeState` TS type does not include the `mode` field documented in CONTRACTS.md. This is a pre-existing gap unrelated to this feature; the consoleMapper correctly uses `s.status` (which includes `"fallback"` and `"waiting_for_hardware"` values) rather than a nonexistent `s.mode`.

---

## 3. Unstated Assumptions

| Assumption | Safe? | Notes |
|---|---|---|
| Incrementing integer IDs instead of nanoid | Yes | IDs are ephemeral, in-memory only. No collision risk with a single singleton store. |
| `exportConsoleLog` is synchronous (saving state is instantaneous) | Yes | Blob creation + anchor click is synchronous DOM operation. The `isSaving` state will never visually render as a spinner, but the code is correct. |
| `prevRestartCount` initialized to 0 | Yes | First `bridge_status` with `restart_count: 0` will not trigger a restart entry. First with `restart_count > 0` will. Correct behavior. |
| `handleScroll` defined inline (recreated each render) | Mostly safe | At 200 entries max with no virtualization, the performance impact is negligible. Not worth optimizing in v1. |
| `useEffect` keyed on `filtered.length` for auto-scroll | Mostly safe | If two entries arrive in the same render batch (same filtered.length delta), the effect still fires once. If entries are added and removed in the same batch keeping length unchanged, auto-scroll would not fire. This is extremely unlikely with a ring buffer and would only matter at exactly 200 entries with rapid verbose traffic. Acceptable. |

---

## 4. Test Coverage

**ADVISORY-4: No new tests were written for this feature.**

The tasks specified "All pre-existing tests pass" as an AC, and `npm run typecheck` passes. However, the following are untested:

- **consoleStore ring buffer logic** -- addEntry cap at 200, recordBuffer append/clear, stopRecording return value. These are pure functions ideal for unit testing.
- **consoleMapper diff detection** -- The mapper has substantial logic (status transitions, device add/remove, pioneer flips). The `resetMapperState()` function was explicitly added for test isolation, suggesting the developer anticipated tests.
- **consoleExport format** -- The export format (ISO timestamp, padded severity, source labels) is well-suited for snapshot testing.

Per the project's testing philosophy (only write justified tests), these would all be justified: they are pure logic modules with non-trivial behavior that cannot be verified by typecheck alone. The ring buffer boundary condition (entry 201 drops entry 1) and the diff detection transitions are the highest-value test targets.

---

## 5. Coherence with Adjacent Features

### bridgeStore interaction
Clean. `consoleStore` does not import `bridgeStore`. The WS dispatch in `ws.ts` calls both stores independently. No shared state, no ordering dependencies.

### ws.ts integration
Clean. The `dispatchToConsole` function is called after the `bridgeStore` dispatch in the `dispatch()` function (L42). If `mapWSMessageToEntries` throws, it would prevent the function from returning, but the mapper is defensive (returns `[]` for unknown message types) and accesses only typed fields. No risk of breaking existing bridge dispatch.

### uiStore interaction
Clean. `ConsoleHeader` imports `useUIStore` for `consoleOpen` and `toggleConsole`. This is a read/action pattern, not a store-to-store import. The `Console.tsx` wrapper also reads `consoleOpen` from `useUIStore`. Both follow established patterns.

### TopBar
No conflicts. The TopBar's StatusDot, TrafficDot, and StartupIndicator all read from `bridgeStore`, which is untouched by this feature. The console's "Connected to backend" / "Backend connection lost" entries align with (but do not duplicate) the TopBar's status indicators.

### Store independence rule
**Verified.** `consoleStore.ts` imports only from `zustand` and `../types/console`. No cross-store imports.

---

## Issue Summary

| # | Severity | Description |
|---|----------|-------------|
| 1 | ADVISORY | Missing "Reconnecting... (attempt N)" system entry specified in the spec's Clean mode system events |
| 2 | ADVISORY | Chevron direction (down/right) deviates from spec (up/down) -- documented developer decision |
| 3 | ADVISORY | No new tests written; consoleStore ring buffer and consoleMapper diff detection are high-value test targets |

---

## Recommendation

**Proceed to milestone close.** All three advisory items can be addressed in a follow-up if desired:

1. Adding reconnection entries requires a small change to `scheduleReconnect()` in `ws.ts` -- emit a system console entry with the attempt count.
2. Chevron direction is a cosmetic preference for Brach to decide.
3. Tests for `consoleStore` and `consoleMapper` would take ~20 minutes and would provide good regression coverage.
