# Session: Cross-Cutting — YAML Config Consolidation
**Date:** 2026-03-17
**Task Reference:** specs/audit-2026-03-17/yaml-config-consolidation.md

## What Changed
| File | Change Type | Description |
|---|---|---|
| `scue/config/__init__.py` | Created | Package init — re-exports all config types and `load_config()` |
| `scue/config/loader.py` | Created | Typed config loader with dataclasses for Server, Bridge (watchdog, health, restart, route), USB configs. `load_config()` entry point. Fail-safe: missing files/keys use defaults. Logs all values at INFO. Port validation (1024–65535). |
| `config/server.yaml` | Created | CORS origins, audio extensions, tracks_dir, cache_path |
| `config/bridge.yaml` | Modified | Added watchdog, health, restart sections (preserving existing fields) |
| `scue/main.py` | Modified | Replaced `_load_bridge_config()` with `load_config()`. Removed hardcoded CORS origins, tracks_dir, cache_path. Passes config to all consumers explicitly. |
| `scue/api/ws.py` | Modified | Accepts `WatchdogConfig` via `init_ws()`. Replaced hardcoded 5000ms threshold and 2.0s poll interval. |
| `scue/api/filesystem.py` | Modified | Added `init_filesystem_api()` to accept audio extensions. Replaced module-level `AUDIO_EXTENSIONS` constant. |
| `scue/api/tracks.py` | Modified | `init_tracks_api()` now accepts `audio_extensions` param. Removed duplicate `AUDIO_EXTENSIONS` constant. |
| `scue/api/usb.py` | Modified | `init_usb_api()` now accepts `UsbConfig`. Replaced hardcoded `_DB_RELATIVE` / `_ANLZ_RELATIVE` with config values. |
| `scue/bridge/manager.py` | Modified | Removed module-level `HEALTH_CHECK_INTERVAL`, `RESTART_BASE_DELAY`, `RESTART_MAX_DELAY`, `MAX_CRASH_BEFORE_FALLBACK` constants. Constructor now accepts `health_check_interval`, `restart_base_delay`, `restart_max_delay`, `max_crash_before_fallback` params with same defaults. |
| `tests/test_bridge/test_manager.py` | Modified | Updated imports — removed references to deleted module-level constants, defined test-local constants with same values. |
| `tests/test_config/__init__.py` | Created | Test package init |
| `tests/test_config/test_loader.py` | Created | 18 tests covering defaults, partial YAML, full override, port validation, audio extensions, USB config, missing dir, malformed YAML |

## Interface Impact
- **BridgeManager constructor**: Added 4 new optional parameters (`health_check_interval`, `restart_base_delay`, `restart_max_delay`, `max_crash_before_fallback`). All have defaults matching previous hardcoded values — fully backward compatible.
- **init_ws()**: Added optional `watchdog_config` parameter. Backward compatible.
- **init_tracks_api()**: Added optional `audio_extensions` parameter. Backward compatible.
- **init_usb_api()**: Added optional `usb_config` parameter. Backward compatible.
- **init_filesystem_api()**: New function. Called from main.py at startup.
- No changes to external contracts (docs/CONTRACTS.md). All WebSocket message shapes unchanged.

## Tests
| Test | Status |
|---|---|
| Pre-existing full suite | ✅ Pass (277 passed, 6 pre-existing failures in test_analysis_edge_cases.py, 11 skipped) |
| test_load_defaults_when_no_yaml (3 tests) | 🆕 ✅ |
| test_load_partial_yaml (3 tests) | 🆕 ✅ |
| test_load_full_yaml (1 test) | 🆕 ✅ |
| test_port_validation (4 tests) | 🆕 ✅ |
| test_audio_extensions_loaded (2 tests) | 🆕 ✅ |
| test_usb_config_loaded (1 test) | 🆕 ✅ |
| test_config_dir_missing (1 test) | 🆕 ✅ |
| test_malformed_yaml (2 tests) | 🆕 ✅ |
| Bridge tests (121 tests) | ✅ Pass (no regressions) |
| **Total new tests:** 18 | **All passing** |

## Decisions Made During Implementation
1. **Port validation uses fallback, not exception.** Invalid ports (outside 1024–65535 or non-integer) log a warning and fall back to default 17400. This matches the fail-safe philosophy: never crash on bad config.
2. **Manager constants became constructor params, not a global config read.** The handoff spec said "pass config explicitly, not as singleton." So BridgeManager's `__init__` accepts the values directly rather than importing from the config module. `main.py` reads config and passes values.
3. **Test file updated for removed constants.** `tests/test_bridge/test_manager.py` imported `MAX_CRASH_BEFORE_FALLBACK`, `RESTART_BASE_DELAY`, `RESTART_MAX_DELAY` as module-level constants from manager.py. Since these were removed, I defined them as test-local constants with the same values. This is in scope since the tests must pass.
4. **`init_filesystem_api()` pattern.** Added a new init function to `filesystem.py` to match the pattern used by other API modules (tracks, usb, bridge). This is the minimal way to inject audio extensions without making it a global import.
5. **Added 2 bonus tests** for malformed YAML resilience (invalid YAML syntax, non-dict root). These verify the fail-safe guarantee.

## Questions for Brach
- None. The spec was unambiguous and implementation was mechanical.

## Remaining Work
- **UI config exposure** is a separate milestone (mentioned in spec). The typed config structure is ready for it.
- **`MAX_CRASH_BEFORE_FALLBACK` placeholder** was already present in manager.py (added by parallel session), absorbed into `config/bridge.yaml` as `restart.max_crash_before_fallback: 3`.
- The 6 pre-existing test failures in `test_analysis_edge_cases.py` are unrelated to this task (Layer 1 analysis edge cases).

## LEARNINGS.md Candidates
None — this was a straightforward config migration with no non-obvious pitfalls.
