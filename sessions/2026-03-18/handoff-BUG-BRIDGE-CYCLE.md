# Handoff Packet: BUG-BRIDGE-CYCLE

## Preamble
Read these files before proceeding:
1. `AGENT_BOOTSTRAP.md`
2. `docs/agents/preambles/COMMON_RULES.md`
3. `docs/agents/preambles/DEVELOPER.md`

## Objective
Fix the bridge crash-restart cycle that occurs when Pioneer hardware connectivity is disrupted, so that the bridge enters a stable waiting state (not an infinite restart loop) and auto-recovers when hardware returns — without user intervention.

## Role
Developer (Bridge — Layer 0)

## Scope Boundary
- Files this agent MAY read/modify:
  - `scue/bridge/manager.py` — primary target: restart logic, health check, fallback trigger
  - `scue/api/ws.py` — only if bridge state broadcasting needs updating (e.g. new status value emitted)
  - `tests/test_bridge/` — add or update tests for new restart behavior
  - `bridge-java/` — read-only, for understanding subprocess behavior and JAR launch flags
- Files this agent must NOT touch:
  - `scue/layer1/` — any file
  - `scue/layer2/` — any file
  - `scue/api/` — any file EXCEPT `ws.py` (and only if required for state broadcasting)
  - `frontend/` — any file (frontend stale state is a separate follow-on task)
  - `scue/network/` — any file
  - `docs/CONTRACTS.md` — read-only

## Context Files
- `AGENT_BOOTSTRAP.md`
- `docs/agents/preambles/COMMON_RULES.md`
- `docs/agents/preambles/DEVELOPER.md`
- `docs/bugs/layer0-bridge.md` — **read this in full before touching any code**; contains reproduction scenarios, root cause hypotheses (4), and acceptance criteria (AC-1 through AC-5)
- `LEARNINGS.md` — Bridge section only
- `docs/CONTRACTS.md` — Layer 0 → Layer 1B section only (for interface impact awareness)

## Background
When Pioneer hardware is disconnected (USB-Ethernet adapter yanked, board powered off) and then reconnected, the bridge enters an unrecoverable crash-restart cycle. Each restart briefly steals macOS window focus ("beat link trigger" flashes in menu bar). The only recovery is a full server restart.

**Root cause hypotheses (from `docs/bugs/layer0-bridge.md`):**
1. No circuit breaker when hardware is absent — bridge oscillates: try → no interface → crash → restart → repeat, indefinitely
2. Health check triggers restart on silence — when hardware disconnects and bridge goes quiet, health check fires a restart unnecessarily
3. `_consecutive_failures` may reset on partial success, preventing fallback from ever triggering
4. Java AWT thread lingers after VirtualCdj.start() failure, confusing Python-side lifecycle

**Key code area:** `_schedule_restart()`, `_health_check_loop()`, `_start_fallback()` in `scue/bridge/manager.py`.

## Constraints
- All pre-existing tests must continue to pass (`tests/test_bridge/`, `tests/test_api/`, full suite).
- Run the test baseline BEFORE making changes; compare after.
- Use `.venv/bin/python` — never bare `python`.
- Do NOT modify Layer 1, the frontend, or any network utilities.
- Do NOT update `docs/CONTRACTS.md` — if an interface change is needed, flag it as `[INTERFACE IMPACT]` in your session summary and stop. Let Orchestrator route to Architect.
- If fixing the crash cycle requires touching the Java subprocess code beyond passing JVM flags at launch, stop and flag it — do not modify Java source.
- Do not introduce busy-wait loops or unconditional sleeps on the async event loop path.
- Update `docs/bugs/layer0-bridge.md` with fix details before ending your session.

## Acceptance Criteria

### AC-1: Graceful hardware disconnect (adapter yank or board power-off)
- [ ] Within 2-3 seconds of hardware disconnect: bridge status transitions to a stable non-cycling state (e.g. `"waiting"`, `"degraded"`, or `"no_hardware"`) — NOT a crash-restart cycle
- [ ] No OS focus stealing occurs after hardware disconnect

### AC-2: Auto-recovery after reconnect
- [ ] When hardware is reconnected, bridge detects restored connectivity and recovers WITHOUT crash-restart cycle and WITHOUT user intervention
- [ ] No manual "Apply and Restart Bridge" required

### AC-3: Bridge restart without hardware present
- [ ] When server starts with no Pioneer hardware present, bridge enters a stable waiting state — NOT a crash-restart cycle
- [ ] Route fix API returns a clear, user-readable error message when the interface doesn't exist (e.g. "Network interface en16 not found — is the USB-Ethernet adapter connected?"), not the raw kernel error "route: bad address: en16"

### AC-4: OS focus behavior (bonus — same session if practical)
- [ ] Java subprocess launch does NOT steal macOS window focus
- [ ] Investigate: pass `-Djava.awt.headless=true` or `-Dapple.awt.UIElement=true` to the JVM at launch (in `manager.py`'s subprocess command). Document which flag(s) work.

### AC-5: App name (bonus — same session if practical)
- [ ] Java process does not identify as "beat link trigger" in the macOS menu bar
- [ ] Investigate: pass `-Xdock:name=SCUE Bridge` JVM flag. Document result.

### Baseline
- [ ] All pre-existing `tests/test_bridge/` tests pass before and after changes

## Implementation Guidance
Start by reading `manager.py` in full before writing any code. Then:

1. **Identify the restart loop:** Trace what happens when `_health_check_loop()` detects silence or `_consecutive_failures` increments — does it ever reach a stable terminal state when hardware is absent?
2. **Add a no-hardware stable state:** The bridge should stop retrying after N consecutive failures (where the Java process exits quickly, indicating no hardware/route) and enter a `"waiting_for_hardware"` state. It should poll at a much lower frequency (e.g., every 30 seconds) for hardware to reappear rather than aggressively restarting.
3. **Decouple health-check silence from restart trigger:** When no Pioneer traffic arrives (hardware silent/off), the health check should NOT trigger a bridge restart — that is normal when hardware is off. Only restart if the bridge process itself has died or the WebSocket connection has dropped.
4. **AC-4/5 (JVM flags):** Once crash cycle is fixed, add JVM flags to the subprocess launch command in `manager.py`. These are low-risk mechanical additions.
5. **AC-3 route error:** Find where the route fix returns the raw kernel error and add a friendly message wrapper.

## Testing Strategy
- Run `tests/test_bridge/` baseline before changes.
- After changes, verify the test suite still passes.
- Add at least one new test covering the "no hardware" stable state (e.g., mock a bridge process that exits immediately N times and assert the manager enters a waiting state rather than continuing to restart).
- If a mock_bridge.py simulation is helpful, use it — `tools/mock_bridge.py` is available for replay.

## Dependencies
- Requires completion of: None (standalone bug fix)
- Blocks: Frontend stale-state fix (separate FE-State task, dispatched after this)

## Follow-On Tasks (NOT in scope for this session)
- **FE-State:** Frontend stale state — devices/players not clearing on hardware disconnect (separate handoff after this fix is validated)
- **DEVELOPER.md:** Add inline-import mock patch tip (small preamble update, Orchestrator will handle)

## Open Questions
None — proceed directly.
