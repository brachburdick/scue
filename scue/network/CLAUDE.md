# Network Module — Agent Context

> Supplements root CLAUDE.md with network-specific conventions, gotchas, and scope.

## Scope

This module handles macOS broadcast route management and cross-platform network interface enumeration for Pro DJ Link connectivity. It is used by `scue/bridge/manager.py` to ensure the correct network interface receives Pioneer device announcements.

**This module does NOT:**
- Handle WebSocket connections (that's `bridge/client.py`)
- Parse Pro DJ Link packets (that's `bridge/fallback.py`)
- Manage the bridge subprocess (that's `bridge/manager.py`)

## Key Files

| File | Purpose |
|------|---------|
| `route.py` | macOS broadcast route inspection (`get_current_route`, `check_route`), route repair (`fix_route`), interface enumeration (`enumerate_interfaces`), sudoers/launchd checks |
| `models.py` | Dataclasses: `InterfaceAddress`, `NetworkInterfaceInfo`, `RouteStatus`, `RouteCheckResult`, `RouteFixResult` |
| `__init__.py` | Public API — re-exports all models and route functions |

## Conventions

- **macOS-only route logic:** `fix_route()` and `get_current_route()` are no-ops on non-macOS platforms. Linux handles link-local routing automatically.
- **Interface scoring:** Replicates the Java bridge's scoring algorithm (link-local +10, ethernet +5, wifi -5, vpn -10). Keep these in sync if the bridge algorithm changes.
- **Subprocess safety:** All subprocess calls (`netstat`, `route get`, sudoers script) have timeouts (5–10s) and exception handling. Never let a hung subprocess block the event loop.
- **Interface name validation:** `fix_route()` validates interface names against `^en\d+$` to prevent command injection via the sudoers script.

## Known Issues

1. **`route get 169.254.255.255` is unreliable on macOS.** Returns stale or wrong results for link-local broadcast addresses. That's why `get_current_route()` uses `netstat -rn` as primary source and `route get` as fallback only. See `docs/bugs/layer0-bridge.md` entry "fix_route() reports failure after successful route add."

2. **Post-fix verification is intentionally relaxed.** After `fix_route()`, we trust the script exit code rather than re-checking with `route get`. The macOS routing table can report the old route even after a successful change. This is logged at DEBUG level, not treated as failure.

## Testing

```bash
python -m pytest tests/test_bridge/test_network_interface.py -v
```

Tests cover interface enumeration, scoring, manager integration, and bridge config loading. Route fix/check tests use mocked subprocess output since they require root privileges.

## Dependencies

- `psutil` — for `net_if_addrs()` and `net_if_stats()` in `enumerate_interfaces()`
- `netifaces` (optional) — fallback interface enumeration in `fallback.py`'s `get_local_interfaces()`
- System: `/usr/local/bin/scue-route-fix` + `/etc/sudoers.d/scue-djlink` for passwordless route fixing
