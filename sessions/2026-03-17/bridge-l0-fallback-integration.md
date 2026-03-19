# Session: Bridge (L0) — Fallback Parser Integration
**Date:** 2026-03-17
**Task Reference:** specs/audit-2026-03-17/fallback-parser-integration.md

## What Changed
| File | Change Type | Description |
|---|---|---|
| `scue/bridge/manager.py` | Modified | Added fallback transition logic: `_start_fallback()`, `_stop_fallback()`, `_fallback_on_message()`, `MAX_CRASH_BEFORE_FALLBACK` constant, `mode` field in `to_status_dict()` |
| `scue/bridge/fallback.py` | Modified | Added optional `interface` parameter to `FallbackParser.__init__()` for interface filtering in `start()` |
| `tests/test_bridge/test_manager.py` | Modified | Updated 5 existing tests for fallback behavior (no_jre/no_jar now → fallback), added 7 new `TestFallbackIntegration` tests |
| `tests/test_bridge/test_fallback.py` | Created | 7 new standalone tests: 5 packet parsing + 2 lifecycle (start/stop, interface filtering) |

## Interface Impact
- `to_status_dict()` now includes a new `mode` field: `"fallback"` or `"bridge"`. Frontend types in `frontend/src/types/bridge.ts` should add this field.
- `no_jre` and `no_jar` are no longer terminal states — the manager transitions to `fallback` instead. Frontend StatusBanner logic that checks for `no_jre`/`no_jar` should be updated (though `fallback` status was already handled with yellow badge per the spec).
- `FallbackParser.__init__()` now accepts an optional `interface: str | None` parameter. No breaking change (parameter is optional with default `None`).

## Tests
| Test | Status |
|---|---|
| Pre-existing bridge tests (108) | ✅ Pass (108/108) |
| test_no_jre_transitions_to_fallback | 🆕 ✅ |
| test_no_jar_transitions_to_fallback | 🆕 ✅ |
| test_stop_from_fallback | 🆕 ✅ |
| test_third_failure_transitions_to_fallback | 🆕 ✅ |
| test_crash_threshold_transitions_to_fallback | 🆕 ✅ |
| test_no_jre_goes_to_fallback_not_retry | 🆕 ✅ |
| test_no_jar_goes_to_fallback_not_retry | 🆕 ✅ |
| test_fallback_messages_flow_through_adapter | 🆕 ✅ |
| test_restart_from_fallback_stops_parser | 🆕 ✅ |
| test_status_dict_reflects_fallback | 🆕 ✅ |
| test_status_dict_mode_bridge_when_running | 🆕 ✅ |
| test_stop_from_fallback_stops_parser | 🆕 ✅ |
| test_start_fallback_sets_state | 🆕 ✅ |
| test_consecutive_failures_preserved_after_fallback_transition | 🆕 ✅ |
| test_fallback_parser_emits_device_found | 🆕 ✅ |
| test_fallback_parser_emits_player_status | 🆕 ✅ |
| test_fallback_parser_emits_beat | 🆕 ✅ |
| test_fallback_parser_callback_fires | 🆕 ✅ |
| test_fallback_parser_ignores_non_magic_packets | 🆕 ✅ |
| test_fallback_parser_start_stop | 🆕 ✅ |
| test_fallback_parser_interface_filtering | 🆕 ✅ |
| **Total** | **121 passed, 0 failed** |

## Decisions Made During Implementation

1. **Added `interface` parameter to `FallbackParser.__init__()`** — The spec noted the manager has `_network_interface` and asked to check how FallbackParser handles it. The parser had no interface parameter, so I added an optional one. When set, `start()` filters `get_local_interfaces()` to only the matching interface name. If no match is found, falls back to `pioneer_interfaces()` discovery. This is a minor, non-breaking change to `fallback.py` (within scope).

2. **`mode` field in `to_status_dict()`** — I chose to always include the `mode` field (values: `"bridge"` or `"fallback"`) rather than only including it when in fallback. This gives the frontend a single field to check rather than inferring mode from the status string.

3. **Updated existing tests rather than keeping old assertions** — The 5 existing tests that asserted `no_jre`/`no_jar` status were updated to assert fallback behavior instead. Old test names like `test_no_jre_state` were renamed to `test_no_jre_transitions_to_fallback` for clarity.

4. **`_stop_fallback()` is called in both `stop()` and `restart()`** — Double-calling is safe since `_stop_fallback()` checks for `None` first. This ensures cleanup regardless of entry path.

## Questions for Brach

1. The `backoff_progression` test was shortened from 7 iterations to 2, since the fallback threshold kicks in at 3. The `backoff_caps_at_max` test was replaced with `crash_threshold_transitions_to_fallback`. I assumed this is acceptable since the exponential backoff math didn't change — only the ceiling is now the fallback threshold. Please confirm.

2. The spec mentions `no_jre`/`no_jar` as states in the state machine docstring. I left them in the docstring since they're still conceptually valid (the manager detects them), but the manager now transitions through them to `fallback` rather than stopping. Should the docstring be updated to remove them, or keep them as intermediate/detection states?

## Remaining Work

- **FE-State agent**: Frontend `bridge.ts` types should add the `mode: "fallback" | "bridge"` field. StatusBanner may need updating if it still has specific `no_jre`/`no_jar` handling.
- **YAML config agent**: Extract `MAX_CRASH_BEFORE_FALLBACK` to `config/bridge.yaml` (along with `RESTART_BASE_DELAY` and `RESTART_MAX_DELAY` which have the same TODO).
- **MILESTONES.md**: Update M0 to note fallback integration is complete.

## LEARNINGS.md Candidates

None — no non-obvious pitfalls encountered. The implementation was straightforward wiring work as predicted.
