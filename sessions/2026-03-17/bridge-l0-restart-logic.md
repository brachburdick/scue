# Session: Bridge (L0) — Restart Logic: Immediate-First-Then-Backoff
**Date:** 2026-03-17
**Task Reference:** Orchestrator task — restart logic improvement

## What Changed

| File | Change Type | Description |
|---|---|---|
| `scue/bridge/manager.py` | Modified | Replaced pure exponential backoff with immediate-first-then-backoff restart logic; added `_consecutive_failures` and `_next_retry_at` state; exposed `restart_attempt` and `next_retry_in_s` in `to_status_dict()` |
| `tests/test_bridge/test_manager.py` | Modified | Added 14 new tests: `TestRestartLogic` (9 tests) and `TestStatusDictRestartFields` (5 tests) |

## Interface Impact

[INTERFACE IMPACT] `bridge_status` WebSocket payload (`to_status_dict()`) gains two new fields:
- `restart_attempt: int` — current consecutive failure count (0 when running normally)
- `next_retry_in_s: float | null` — seconds until next restart attempt (null when running or not retrying)

These are additive (backwards-compatible). The FE-State agent should add these to the TypeScript `BridgeStatus` type.

The existing `restart_count` field is preserved and now backed by the same `_consecutive_failures` value.

## Tests

| Test | Status |
|---|---|
| All 94 pre-existing bridge tests | ✅ Pass |
| `TestRestartLogic::test_first_failure_immediate_retry` | 🆕 ✅ |
| `TestRestartLogic::test_second_failure_base_backoff` | 🆕 ✅ |
| `TestRestartLogic::test_third_failure_doubled_backoff` | 🆕 ✅ |
| `TestRestartLogic::test_backoff_caps_at_max` | 🆕 ✅ |
| `TestRestartLogic::test_success_resets_failure_counter` | 🆕 ✅ |
| `TestRestartLogic::test_after_reset_next_crash_is_immediate` | 🆕 ✅ |
| `TestRestartLogic::test_no_jre_does_not_retry` | 🆕 ✅ |
| `TestRestartLogic::test_no_jar_does_not_retry` | 🆕 ✅ |
| `TestRestartLogic::test_backoff_progression` | 🆕 ✅ |
| `TestStatusDictRestartFields::test_running_state_has_zero_restart_fields` | 🆕 ✅ |
| `TestStatusDictRestartFields::test_crashed_state_shows_failure_count` | 🆕 ✅ |
| `TestStatusDictRestartFields::test_next_retry_in_s_when_waiting` | 🆕 ✅ |
| `TestStatusDictRestartFields::test_next_retry_in_s_clamps_to_zero` | 🆕 ✅ |
| `TestStatusDictRestartFields::test_restart_count_backward_compat` | 🆕 ✅ |

**Total: 108 passed, 0 failed**

## Decisions Made During Implementation

1. **Added `_restart_count` property alias rather than updating `test_network_interface.py`** — that file is outside the modify scope. The property delegates to `_consecutive_failures`, so existing code referencing `_restart_count` continues to work. If this is wrong, the property can be removed and the test updated by the appropriate agent.

2. **`_notify_state_change()` only called when delay > 0** — For the immediate retry case (delay=0), there's no useful intermediate state to broadcast. The next `start()` call notifies on its own. If the FE needs a "retrying now" flash, this can be added later.

3. **Backoff formula: `base_delay * 2^(failures-2)`** — Gives the sequence 0, 2, 4, 8, 16, 30, 30... matching the spec exactly (first=immediate, second=base, third=2×base, etc.).

## Questions for Brach

None — spec was clear.

## Remaining Work

- **FE-State agent**: Add `restart_attempt: number` and `next_retry_in_s: number | null` to TypeScript `BridgeStatus` type in `frontend/src/types/`.
- **Config extraction task**: Move `RESTART_BASE_DELAY` (2.0s) and `RESTART_MAX_DELAY` (30.0s) to `config/bridge.yaml` (marked with TODO comments in code).
- **Fallback integration task**: Add "give up after N failures" behavior on top of this.

## LEARNINGS.md Candidates

- **Renaming private attributes can break tests in other files** — `test_network_interface.py` referenced `_restart_count` directly. Adding a property alias was the safest fix without touching out-of-scope files. Future agents: prefer backward-compat aliases when renaming internals that other test files may reference.
