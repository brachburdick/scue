# Handoff Packet: FIX-SC007-ROUTE-API

## Objective
`POST /api/network/route/fix` must return a user-friendly error message (not raw kernel output)
when the requested interface does not exist (e.g., USB-Ethernet adapter unplugged).

## Role
Developer (Bridge / L0)

## Scope Boundary
- Files this agent MAY read/modify:
  - `scue/api/network.py` — the endpoint to fix
  - `scue/bridge/manager.py` — reference only: the friendly error wrapping already lives here (lines 296–308)
  - `tests/test_api/test_bridge_api.py` — add regression test
- Files this agent must NOT touch:
  - `scue/network/route.py` — do NOT modify the underlying route module
  - `scue/bridge/adapter.py`, `scue/bridge/messages.py` — out of scope
  - Any frontend files
  - Any other test files

## Context Files
- `AGENT_BOOTSTRAP.md`
- `docs/agents/preambles/COMMON_RULES.md`
- `docs/agents/preambles/DEVELOPER.md`
- `docs/bugs/layer0-bridge.md` — the original bug entry; see root cause 5 ("Route fix error message was raw kernel output")
- `docs/qa-verdicts/bridge-lifecycle-2026-03-18.md` — QA Verdict documenting the failure
- `LEARNINGS.md` — read before starting

## Background
The BUG-BRIDGE-CYCLE fix (2026-03-18) wrapped "bad address" kernel errors with a
user-friendly message inside `BridgeManager.fix_route()` (`scue/bridge/manager.py:296–308`).
However, the REST endpoint `fix_route_endpoint()` in `scue/api/network.py:114` calls
`scue.network.route.fix_route()` directly, bypassing the manager method entirely. The
friendly wrapping was never reached by the API path.

**Observed failure:**
```
POST /api/network/route/fix {"interface": "en16"}
→ HTTP 500 {"detail": {"success": false, "error": "route: bad address: en16", ...}}
```

**Expected:**
```
→ HTTP 500 {"detail": {"success": false, "error": "Network interface 'en16' is not available. Make sure your USB-Ethernet adapter is connected.", ...}}
```
(or similar user-readable message — exact wording may be adjusted)

## Constraints
- Do NOT modify `scue/network/route.py`.
- Do NOT change the response schema of `POST /api/network/route/fix` — keep existing fields
  (`success`, `error`, `previous_interface`, `new_interface`). Only the `error` string content changes.
- The fix must handle "bad address" errors from the kernel. Check `manager.py:296–308` for the
  exact string matching pattern already in use — reuse or adapt it.
- All pre-existing tests must continue to pass.
- Type hints required on any modified function signatures.
- No print() — use logging module.

## Acceptance Criteria
- [ ] `POST /api/network/route/fix {"interface": "en16"}` (non-existent interface) returns a
      user-readable error string — NOT raw kernel output like "route: bad address: en16".
- [ ] The response HTTP status code and schema shape are unchanged (still 500 with `detail` object).
- [ ] A regression test in `tests/test_api/test_bridge_api.py` covers this case: mock a
      "bad address" error from `fix_route()` and assert the response contains a friendly message.
- [ ] All 136 pre-existing tests pass.
- [ ] `POST /api/network/route/fix` with a valid interface continues to work correctly (no regression).

## Dependencies
- Requires completion of: none
- Blocks: QA re-test of SC-007 (targeted re-run, SC-007 only)

## Open Questions
None. The fix path is clear: apply "bad address" wrapping in `fix_route_endpoint()` before
raising HTTPException, matching the pattern already used in `manager.py:296–308`.
