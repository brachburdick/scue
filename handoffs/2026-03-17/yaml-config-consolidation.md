# SCUE Agent Preamble — Include at the Top of Every Agent Session

> Paste this before the handoff packet in every new agent conversation.
> It establishes the behavioral contract that all agents must follow.

---

You are a specialized agent working on the SCUE project — a DJ lighting automation system. You are part of a multi-agent team where each agent has a defined scope. You will receive a **Handoff Packet** that defines your objective, scope, constraints, and acceptance criteria for this session.

## Your Behavioral Contract

### 1. Scope Discipline
- You may ONLY read and modify files listed in your handoff's "Scope" section.
- If completing your task requires touching a file outside your scope, **STOP and tell Brach.** Do not proceed. Explain what you need and why, and let Brach decide whether to expand your scope or dispatch a different agent.
- If you discover a bug or issue outside your scope, note it in your session summary under "Remaining Work" — do not fix it.

### 2. Ask, Don't Assume
- If the spec, plan, or constraints are ambiguous on any point, **ask Brach before proceeding.**
- Frame your question as: "The spec says [X], but it's unclear whether [Y or Z]. My assumption would be [Y] because [reason]. Should I proceed with that, or do you want something different?"
- It is ALWAYS better to ask one question and wait than to implement the wrong thing and need to redo it.

### 3. Decision Transparency
- If you make any judgment call during implementation (choosing between two valid approaches, interpreting an edge case, selecting a default value), **document it** in your session summary under "Decisions Made During Implementation."
- Format: "I chose [X] over [Y] because [reason]. If this is wrong, [describe what would need to change]."

### 4. Proactive Concern Flagging
- If you notice something that seems wrong, risky, or inconsistent with the architecture — even if it's technically outside your current task — flag it. Use: **[CONCERN]** followed by a brief description.
- If a design or infrastructure decision could go multiple ways and you think Brach should weigh in, use: **[DECISION OPPORTUNITY]** followed by the options and your recommendation.

### 5. Session Summary (Non-Negotiable)
- Before ending every session, produce a **Session Summary** in this exact format:

```markdown
# Session: [Your Role] — [Task Title]
**Date:** [Today's date]
**Task Reference:** [specs/*/tasks.md task number, if applicable]

## What Changed
| File | Change Type | Description |
|---|---|---|
| [path] | Created / Modified / Deleted | [One line] |

## Interface Impact
[Any changes to types, API shapes, or contracts. "None" if no changes.]

## Tests
| Test | Status |
|---|---|
| [test name or file] | ✅ Pass / ❌ Fail / 🆕 New |

## Decisions Made During Implementation
[Judgment calls. Format: "I chose X over Y because Z."]

## Questions for Brach
[Anything uncertain. Format: "I assumed X because Y. Please confirm or correct."]

## Remaining Work
[Anything not finished, or discovered issues outside scope.]

## LEARNINGS.md Candidates
[Non-obvious pitfalls or behaviors worth documenting for future agents.]
```

### 6. Contract Awareness
- Before modifying any data structure that appears in `docs/CONTRACTS.md`, check whether your change is backwards-compatible.
- If it's not, flag it as **[INTERFACE IMPACT]** and describe the change. Do NOT update CONTRACTS.md yourself — that's coordinated through the Architect.
- If you're creating a new type/interface that other layers will consume, define it explicitly (exact field names, types, optional/required) and include it in your session summary.

---

## Addendum: Environment & Session Artifacts

Read the full addendum from disk: **`docs/agents/AGENT_PREAMBLE_ADDENDUM.md`**

Key points:
- Use `.venv/bin/python` for all Python commands (not bare `python`)
- Run the full test suite BEFORE and AFTER changes to establish baseline
- Write session summary to `sessions/2026-03-17/yaml-config-consolidation.md`
- Append any LEARNINGS.md entries to `LEARNINGS.md` in project root
- Flag any preamble improvement candidates in session summary

---

## Now: Read your Handoff Packet below and confirm your understanding before starting.

---

# Handoff Packet: YAML Config Consolidation

## Objective

Eliminate hardcoded configuration values across the codebase by creating a typed config loader module and consolidating all settings into YAML files under `config/`. This enforces the project rule from CLAUDE.md: *"All configuration is YAML files in config/. No hardcoded values."*

## Context Documents (read from disk)

- Read `specs/audit-2026-03-17/yaml-config-consolidation.md` — **the full task spec with hardcoded values inventory, proposed config structure, and implementation notes**
- Read `sessions/bridge-l0-restart-logic-2026-03-17.md` — prior session that added `RESTART_BASE_DELAY` and `RESTART_MAX_DELAY` constants with TODO comments to move to config
- Read `CLAUDE.md` — project conventions (especially the "All configuration is YAML" rule)
- Read `docs/CONTRACTS.md` — for understanding any type impacts
- Read `LEARNINGS.md` — known pitfalls
- Read `docs/agents/AGENT_PREAMBLE_ADDENDUM.md` — environment setup instructions

## Prior Session Context

A Bridge L0 session on 2026-03-17 added two constants to `manager.py`:
- Line 30: `RESTART_BASE_DELAY = 2.0` — with TODO comment to move to config/bridge.yaml
- Line 31: `RESTART_MAX_DELAY = 30.0` — with TODO comment to move to config/bridge.yaml

These should be absorbed into `config/bridge.yaml` under a new `restart:` section as part of this task.

**Note:** A parallel Bridge L0 session may also add `MAX_CRASH_BEFORE_FALLBACK` to manager.py. If you see this constant when reading manager.py, absorb it into config/bridge.yaml as well. If it doesn't exist yet, add a placeholder in bridge.yaml (`max_crash_before_fallback: 3`) for the fallback integration task to consume later.

## Scope

### Files to READ (do not modify):
- `specs/audit-2026-03-17/yaml-config-consolidation.md` — full spec
- `sessions/bridge-l0-restart-logic-2026-03-17.md` — prior session
- `CLAUDE.md` — project rules
- `docs/CONTRACTS.md`
- `LEARNINGS.md`

### Files to CREATE:
- `scue/config/__init__.py` — package init
- `scue/config/loader.py` — typed config loading with dataclasses
- `config/server.yaml` — CORS origins, audio extensions, paths

### Files to MODIFY:
- `config/bridge.yaml` — extend with watchdog, health, restart sections
- `scue/main.py` — use config loader instead of inline YAML loading
- `scue/api/ws.py` — read watchdog thresholds from config
- `scue/api/filesystem.py` — read audio extensions from config
- `scue/api/tracks.py` — read audio extensions from config (remove duplicate)
- `scue/api/usb.py` — read USB paths from config/usb.yaml
- `scue/bridge/manager.py` — read health check and restart constants from config

### Files to NOT touch:
- `scue/layer1/` — Layer 1 internals
- `frontend/` — frontend code
- `scue/bridge/adapter.py`, `scue/bridge/messages.py`, `scue/bridge/client.py` — bridge internals
- `scue/bridge/fallback.py` — fallback parser
- `docs/CONTRACTS.md` — flag any impacts in session summary
- `config/usb.yaml` — this file already exists with correct content; wire it up in `usb.py`, don't modify the YAML itself

### Tests to CREATE:
- `tests/test_config/` — new test directory
- `tests/test_config/test_loader.py` — config loader tests

## Hardcoded Values Inventory

Read the full inventory in `specs/audit-2026-03-17/yaml-config-consolidation.md`. Summary:

| Value | Current Location | Target Config |
|-------|-----------------|---------------|
| CORS origins `["http://localhost:5173"]` | `main.py:27` | `config/server.yaml` → `server.cors_origins` |
| Audio extensions `.mp3,.wav,.flac,.aiff,.m4a,.ogg` | `api/filesystem.py:11`, `api/tracks.py:29` | `config/server.yaml` → `server.audio_extensions` |
| Default tracks dir `Path("tracks")` | `main.py:42` | `config/server.yaml` → `server.tracks_dir` |
| Default cache path `Path("cache/scue.db")` | `main.py:43` | `config/server.yaml` → `server.cache_path` |
| Pioneer USB paths | `api/usb.py:25-26` | Load from existing `config/usb.yaml` |
| Pioneer status watchdog threshold `5000ms` | `api/ws.py` (~line 67/74) | `config/bridge.yaml` → `bridge.watchdog.is_receiving_threshold_ms` |
| Pioneer status poll interval `2.0s` | `api/ws.py` (~line 112) | `config/bridge.yaml` → `bridge.watchdog.poll_interval_s` |
| Health check interval `10.0s` | `bridge/manager.py:27` | `config/bridge.yaml` → `bridge.health.check_interval_s` |
| Max backoff `30.0s` | `bridge/manager.py:31` | `config/bridge.yaml` → `bridge.restart.max_delay_s` |
| Restart base delay `2.0s` | `bridge/manager.py:30` | `config/bridge.yaml` → `bridge.restart.base_delay_s` |

## Implementation Plan

### Step 1: Create `scue/config/loader.py`

Design a config loader module with these properties:

1. **Typed config via dataclasses** — each YAML file maps to a dataclass:

```python
@dataclass
class ServerConfig:
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    audio_extensions: list[str] = field(default_factory=lambda: [".mp3", ".wav", ".flac", ".aiff", ".m4a", ".ogg"])
    tracks_dir: str = "tracks"
    cache_path: str = "cache/scue.db"

@dataclass
class WatchdogConfig:
    is_receiving_threshold_ms: int = 5000
    poll_interval_s: float = 2.0

@dataclass
class HealthConfig:
    check_interval_s: float = 10.0

@dataclass
class RestartConfig:
    base_delay_s: float = 2.0
    max_delay_s: float = 30.0
    max_crash_before_fallback: int = 3

@dataclass
class RouteConfig:
    auto_fix: bool = True
    launchd_installed: bool = False

@dataclass
class BridgeConfig:
    network_interface: str | None = None
    player_number: int = 5
    port: int = 17400
    route: RouteConfig = field(default_factory=RouteConfig)
    watchdog: WatchdogConfig = field(default_factory=WatchdogConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    restart: RestartConfig = field(default_factory=RestartConfig)

@dataclass
class UsbConfig:
    db_relative_path: str = "PIONEER/rekordbox/exportLibrary.db"
    anlz_relative_path: str = "PIONEER/USBANLZ"

@dataclass
class ScueConfig:
    server: ServerConfig
    bridge: BridgeConfig
    usb: UsbConfig
```

2. **Fail-safe loading** — missing YAML files or missing keys fall back to defaults. Never crash on missing config.

3. **`load_config(config_dir: Path = Path("config")) -> ScueConfig`** — the main entry point. Loads `server.yaml`, `bridge.yaml`, `usb.yaml` from the directory. Returns a fully populated `ScueConfig` with defaults filled in.

4. **Log all values at startup** — after loading, log every config value at INFO level so they're visible in server startup output.

### Step 2: Create `config/server.yaml`

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

### Step 3: Extend `config/bridge.yaml`

Add these sections to the existing file (preserve existing `bridge.network_interface`, `bridge.player_number`, `bridge.port`, `bridge.route`):

```yaml
bridge:
  # ... existing fields ...
  watchdog:
    is_receiving_threshold_ms: 5000
    poll_interval_s: 2.0
  health:
    check_interval_s: 10.0
  restart:
    base_delay_s: 2.0
    max_delay_s: 30.0
    max_crash_before_fallback: 3
```

### Step 4: Wire config into consumers

Replace each hardcoded value with a read from the config object. The config object should be loaded once in `main.py` and passed to each consumer.

**Pattern for passing config:**

```python
# main.py
from scue.config.loader import load_config

config = load_config()

# Pass to manager
manager = BridgeManager(
    ...
    health_check_interval=config.bridge.health.check_interval_s,
    restart_base_delay=config.bridge.restart.base_delay_s,
    restart_max_delay=config.bridge.restart.max_delay_s,
)

# Pass to WS manager
init_ws(app, manager, config.bridge.watchdog)

# Pass to API routers
init_tracks_api(app, ..., audio_extensions=config.server.audio_extensions)
```

**Important:** Do not make config a global singleton. Pass it explicitly to consumers. This makes testing easier and dependencies visible.

### Step 5: Remove duplicates

- `api/filesystem.py` and `api/tracks.py` both define `AUDIO_EXTENSIONS`. Remove both. Each should receive the extension list from config via `main.py`.

## Test Plan

### New tests in `tests/test_config/test_loader.py`:

- [ ] `test_load_defaults_when_no_yaml` — config loader returns all defaults when YAML files don't exist
- [ ] `test_load_partial_yaml` — config loader merges partial YAML with defaults (e.g., bridge.yaml has `port` but no `watchdog` → watchdog gets defaults)
- [ ] `test_load_full_yaml` — all values from YAML override defaults
- [ ] `test_port_validation` — port outside 1024-65535 raises or clamps (your choice — document the decision)
- [ ] `test_audio_extensions_loaded` — audio extensions from server.yaml are loaded correctly
- [ ] `test_usb_config_loaded` — USB paths from usb.yaml are loaded correctly
- [ ] `test_config_dir_missing` — missing config directory returns all defaults (no crash)

### Existing tests (baseline — must still pass):

Run the full test suite (`tests/`) and record the count. All pre-existing tests must still pass. Config changes should be transparent — same values, different source.

## Acceptance Criteria

- [ ] `scue/config/loader.py` exists with typed dataclasses and `load_config()` function
- [ ] `config/server.yaml` exists with CORS, audio extensions, paths
- [ ] `config/bridge.yaml` extended with watchdog, health, restart sections
- [ ] Zero hardcoded config values remain in Python source — verify with grep:
  ```bash
  # Should find NO matches in .py files (only in .yaml and tests)
  grep -rn "5173\|AUDIO_EXTENSIONS\|HEALTH_CHECK_INTERVAL\|RESTART_BASE_DELAY\|RESTART_MAX_DELAY" scue/ --include="*.py" | grep -v config/
  ```
- [ ] `config/usb.yaml` is loaded and used by `api/usb.py`
- [ ] All config values logged at startup (INFO level)
- [ ] Server starts correctly with `config/` directory containing all YAML files
- [ ] Server starts correctly with empty `config/` directory (all defaults work)
- [ ] All pre-existing tests pass
- [ ] New config tests pass (≥7 tests)
- [ ] `api/filesystem.py` and `api/tracks.py` no longer have duplicate `AUDIO_EXTENSIONS`

## Important Notes

- **Do not change the values** — this is a source-of-truth migration, not a tuning exercise. The hardcoded values become the YAML defaults.
- **Config is not a global singleton** — pass it explicitly via function parameters or init functions.
- **YAML loading uses `pyyaml`** — already a project dependency (used by existing bridge config loading in `main.py`).
- **The existing `_load_bridge_config()` function in `main.py`** should be replaced by the new config loader. It currently does ad-hoc YAML loading — the new loader subsumes it.

## Estimated Complexity

**Medium-Large** (~45 min). Many files touched but changes are mechanical (replace constant with config read). The config loader itself is the main design work.

## Session Summary Format

Write to: **`sessions/2026-03-17/yaml-config-consolidation.md`**

```markdown
# Session: Cross-Cutting — YAML Config Consolidation
**Date:** 2026-03-17

## What Changed
| File | Change Type | Description |
|---|---|---|
| [path] | Created/Modified | [One line] |

## Interface Impact
[Any changes to how components are initialized or configured. Likely "None" for external contracts, but internal wiring changes.]

## Tests
| Test | Status |
|---|---|
| Pre-existing full suite | ✅ Pass (count) |
| [new test name] | 🆕 ✅ |

## Decisions Made During Implementation
[Config structure choices, validation approach, error handling for bad YAML, etc.]

## Questions for Brach
[Any uncertainties about config structure or defaults.]

## Remaining Work
[e.g., "UI config exposure is a separate milestone", "MAX_CRASH_BEFORE_FALLBACK placeholder added for fallback task"]

## LEARNINGS.md Candidates
[Any non-obvious pitfalls discovered during config migration.]
```
