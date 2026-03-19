# Task Spec: YAML Configuration Consolidation

**Source:** Audit 2026-03-17, Domain D (API/Config)
**Priority:** Hygiene (project rule: "All configuration is YAML files in config/. No hardcoded values.")
**Touches:** `config/`, `scue/main.py`, `scue/api/` (multiple routers)
**Layer boundary:** Cross-cutting — touches API layer and main entry point

## Problem

The project's own CLAUDE.md states: "All configuration is YAML files in config/. No hardcoded values." Several values are currently hardcoded across the codebase, and one config file (`config/usb.yaml`) exists but is never loaded.

## Hardcoded Values Inventory

| Value | Current Location | Should Be |
|-------|-----------------|-----------|
| CORS origins `["http://localhost:5173"]` | `main.py:27` | `config/server.yaml` |
| Audio extensions `.mp3,.wav,.flac,.aiff,.m4a,.ogg` | `api/filesystem.py:11`, `api/tracks.py:29` | `config/server.yaml` (single source) |
| Default tracks dir `Path("tracks")` | `main.py` | `config/server.yaml` |
| Default cache path `Path("cache/scue.db")` | `main.py` | `config/server.yaml` |
| Pioneer USB paths | `api/usb.py:25-26` | Load from existing `config/usb.yaml` |
| Pioneer status watchdog threshold `5000ms` | `api/ws.py:56` | `config/bridge.yaml` under `watchdog:` |
| Pioneer status poll interval `2.0s` | `api/ws.py:93` | `config/bridge.yaml` under `watchdog:` |
| Health check interval `10.0s` | `bridge/manager.py:27` | `config/bridge.yaml` |
| Max backoff `30.0s` | `bridge/manager.py:28` | `config/bridge.yaml` |

## Proposed Config File Structure

### `config/server.yaml` (NEW)
```yaml
server:
  cors_origins:
    - "http://localhost:5173"
  audio_extensions:
    - ".mp3"
    - ".wav"
    - ".flac"
    - ".aiff"
    - ".m4a"
    - ".ogg"
  tracks_dir: "tracks"
  cache_path: "cache/scue.db"
```

### `config/bridge.yaml` (EXTEND)
```yaml
bridge:
  network_interface: en16
  player_number: 5
  port: 17400
  route:
    auto_fix: true
    launchd_installed: false
  watchdog:
    is_receiving_threshold_ms: 5000
    poll_interval_s: 2.0
  health:
    check_interval_s: 10.0
    max_backoff_s: 30.0
    max_crash_restarts: 3  # before falling to fallback
```

### `config/usb.yaml` (FIX — wire up existing file)
```yaml
usb:
  db_relative_path: "PIONEER/rekordbox/exportLibrary.db"
  anlz_relative_path: "PIONEER/USBANLZ"
```

## UI-Accessible vs Internal Configuration

This is a design question for a future milestone, but worth capturing the initial classification now:

### UI-Accessible (user/DJ should be able to change via frontend)
- **Network interface** — already exposed via Bridge page
- **Bridge port** — could be useful if port conflicts arise
- **Auto-fix route** — toggle in Network page
- **Tracks directory** — exposed via AnalyzePanel scan path
- **Audio extensions** — user might want to add `.opus` etc.

### Internal Only (developer/deployment config, NOT exposed in UI)
- **CORS origins** — deployment concern, not DJ-facing
- **Cache path** — internal plumbing
- **Watchdog thresholds** — tuning parameters, not user-facing
- **Health check intervals** — operational, not user-facing
- **Max backoff / crash restart count** — operational

### Future Decision Needed
- **Player number** — Currently in bridge.yaml. Could be UI-accessible for multi-SCUE setups.
- **USB paths** — Template paths for Pioneer USB. Power users might want to override.

> **Note:** The UI-accessible config question is a larger design task (which pages expose which settings, validation, restart-required flags). This spec only covers consolidating hardcoded values into YAML. The UI exposure can be a separate milestone item.

## Implementation Notes

- Create a `scue/config/loader.py` module that loads all YAML files at startup and exposes typed config objects (dataclasses)
- All routers import from the config module, not from raw YAML loading
- Config loading should be fail-safe: missing keys fall back to defaults, missing files use all defaults
- Log every config value at startup (INFO level) for debuggability
- Validate port ranges, path existence, etc. at load time

## Test Plan

- [ ] Unit: Config loader returns defaults when YAML files missing
- [ ] Unit: Config loader merges partial YAML with defaults
- [ ] Unit: Port validation (1024–65535)
- [ ] Unit: Audio extensions list is respected by filesystem browser and track scanner
- [ ] Integration: Server starts correctly with fresh `config/` directory (all defaults)

## Files to Modify

| File | Change |
|------|--------|
| `config/server.yaml` | NEW |
| `config/bridge.yaml` | Extend with watchdog + health sections |
| `scue/config/loader.py` | NEW — typed config loading |
| `scue/main.py` | Use config loader instead of inline YAML loading |
| `scue/api/ws.py` | Read thresholds from config |
| `scue/api/filesystem.py` | Read audio extensions from config |
| `scue/api/tracks.py` | Read audio extensions from config |
| `scue/api/usb.py` | Read USB paths from `config/usb.yaml` |
| `scue/bridge/manager.py` | Read health check constants from config |

## Acceptance Criteria

- Zero hardcoded config values in Python source (grep for magic numbers confirms)
- All config values logged at startup
- Server starts with empty `config/` directory (all defaults work)
- `config/usb.yaml` is actually loaded and used
- Existing behavior unchanged (values are the same, just sourced from YAML)
