# Bridge Lifecycle Redesign

Status: **APPROVED** (2026-03-31)

## Problem

The current bridge architecture is bridge-first: it launches immediately on app start, hunts for hardware, crashes when nothing is found, and enters retry/backoff loops. This causes:
- Crash loops when no hardware is connected (normal dev scenario)
- Hardcoded interface (en16) fails silently when hardware is on en7
- Total state wipeout on hardware disconnect
- 8+ UI states that are confusing and overlap
- Boot-loop on auto-restart that doesn't resolve even when hardware returns

## Design: Hardware-First, Event-Driven

### Three Layers

```
┌──────────────────────────────────────────────────────┐
│              1. INTERFACE WATCHER                     │
│  (Python, always running, ~zero cost)                │
│                                                      │
│  Monitors OS network interfaces for link-local       │
│  address changes (169.254.x.x). When a new           │
│  link-local addr appears → emits iface_up(name).     │
│  When link-local addr disappears → iface_down(name). │
│                                                      │
│  Implementation: psutil.net_if_addrs() poll every    │
│  2-3s, or macOS SCDynamicStore callback.             │
└───────────────────────┬──────────────────────────────┘
                        │ iface_up / iface_down events
                        ▼
┌──────────────────────────────────────────────────────┐
│              2. PIONEER PROBE                         │
│  (Python, runs only on iface_up)                     │
│                                                      │
│  Sends a Pro DJ Link device query on the interface.  │
│  Listens for announcement response (timeout ~2s).    │
│  If Pioneer device responds → pioneer_found(iface,   │
│    device_info). If no response → ignore.            │
│                                                      │
│  Also triggered on periodic re-check when in         │
│  DISCONNECTED state and interface still has           │
│  link-local addr (hardware power-cycled, same port). │
└───────────────────────┬──────────────────────────────┘
                        │ pioneer_found / pioneer_lost
                        ▼
┌──────────────────────────────────────────────────────┐
│              3. BRIDGE MANAGER                        │
│  (existing, but simplified & reactive)               │
│                                                      │
│  Only acts on events from layers above.              │
│  Manages Java subprocess lifecycle.                  │
│  Preserves stale state on disconnect.                │
│  Auto-fixes route silently before connecting.        │
│  Cleans up stale Java processes before starting.     │
└──────────────────────────────────────────────────────┘
```

### State Machine (5 states, down from 8+)

| State | Meaning | Bridge subprocess | UI |
|---|---|---|---|
| **IDLE** | No Pioneer hardware detected on any interface | Not running | Gray dot, "No Pioneer hardware detected" |
| **CONNECTING** | Hardware found, bridge starting on detected interface | Launching | Yellow pulse, "Connecting to [device] on [iface]..." |
| **CONNECTED** | Bridge running, receiving data | Running | Green dot, device/player info live |
| **DISCONNECTED** | Hardware was connected, now gone. Last-known state preserved. | Stopped (clean) | Gray dot, stale state greyed out, "Hardware disconnected" badge |
| **ERROR** | Genuine bridge failure (JVM crash, bad JAR, port conflict) | Crashed | Red dot, error detail, auto-retrying |

### Removed States

| Old State | Replacement |
|---|---|
| `crashed` (normal flow) | DISCONNECTED (hw absence) or ERROR (genuine crash) |
| `waiting_for_hardware` | IDLE + interface watcher (event-driven, no polling) |
| `starting` | CONNECTING (same thing, clearer name) |
| `no_jre` / `no_jar` | Pre-boot checks, not runtime states. Setup error page. |
| `fallback` | Evaluate after QA — may become the hardware monitor |
| `not_initialized` | App starts in IDLE |

### Transition Table

| From | Event | To | Action |
|---|---|---|---|
| IDLE | pioneer_found(iface) | CONNECTING | Fix route silently, kill stale Java, launch bridge |
| CONNECTING | bridge ready + first msg | CONNECTED | Populate devices/players, green dot |
| CONNECTING | timeout (10s) or launch fail | ERROR | Log reason, attempt retry |
| CONNECTING | iface_down / user cancels | IDLE | Abort launch, clean up |
| CONNECTED | pioneer_lost (5s no announcements) | DISCONNECTED | Stop bridge cleanly, freeze state |
| CONNECTED | genuine JVM crash / WS death | ERROR | Preserve state, begin auto-restart |
| CONNECTED | pioneer_found(other_iface) | CONNECTED | Add to known-hardware set, show switcher. Do NOT auto-switch. |
| CONNECTED | user selects different hardware | CONNECTING | Disconnect current, connect to selected |
| CONNECTED | user stops manually | IDLE | Clean shutdown, clear state |
| DISCONNECTED | pioneer_found(any_iface) | CONNECTING | Silent reconnect |
| DISCONNECTED | iface_down (all pioneer ifaces) | IDLE | Clear stale state |
| ERROR | auto-restart succeeds | CONNECTED | Resume |
| ERROR | pioneer_lost (hw gone during error) | IDLE | Stop retrying |
| ERROR | 3 retries exhausted | ERROR (stuck) | Surface to user, wait for manual action or new pioneer_found |
| ERROR | pioneer_found (after retries exhausted) | CONNECTING | Fresh attempt |

### Pre-Bridge Checks (app boot, not runtime)

- JRE available? → Setup banner if missing
- Bridge JAR exists? → Setup banner if missing

### Route Handling

On pioneer_found(iface):
1. Check route for 169.254.255.255
2. Points to correct iface? → proceed
3. Wrong? → silently fix → proceed
4. Fix failed? → log warning, proceed anyway
5. Route status visible on Bridge page for debugging

### Multi-Hardware

- First detected → auto-connect
- Additional detected → switcher in TopBar + Bridge page
- Does NOT hijack existing connection
- Switching = disconnect current → connect to selected

### Hardware Disconnect UX

- Features that require live hardware: freeze/grey out
- Features that can work offline: indicate disconnection but remain interactive
- Stale device/player state preserved until reconnect or user clears

### Error Auto-Restart

- Kill stale Java processes before each attempt
- Max 3 retries
- If hardware confirmed present via watcher → evidence retry should work
- If hardware gone during ERROR → stop retrying, go to IDLE
