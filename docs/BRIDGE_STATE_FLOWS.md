# Bridge State Flows — Every Path, Every Silo

> Complete reference for what happens at each layer (Java Bridge, Python BE, React FE)
> for every possible starting state and hardware event.

---

## 1. Master State Machine

```
                              ┌─────────────────────────────────────────────┐
                              │           BRIDGE MANAGER STATES             │
                              ├─────────────────────────────────────────────┤
                              │                                             │
     ┌──────┐   start()       │  ┌──────────┐  success   ┌─────────┐      │
     │STOPPED├───────────────────►│ STARTING ├───────────►│ RUNNING │      │
     └──────┘                 │  └────┬─────┘            └────┬────┘      │
                              │       │ fail                   │           │
                              │       ▼                        │ crash     │
                              │  ┌─────────┐  backoff retry   │ or WS     │
                              │  │ CRASHED  │◄─────────────────┘ silence   │
                              │  └────┬────┘                   (>20s)     │
                              │       │                                    │
                              │       │ 3 consecutive crashes              │
                              │       │ (each <30s uptime)                 │
                              │       ▼                                    │
                              │  ┌──────────────────────┐                  │
                              │  │ WAITING_FOR_HARDWARE  │  poll 30s       │
                              │  │   (slow poll mode)    ├──────┐          │
                              │  └──────────┬───────────┘      │          │
                              │             │ interface found   │ no iface │
                              │             ▼                   │          │
                              │        ┌──────────┐            │          │
                              │        │ STARTING ├────────────┘          │
                              │        └──────────┘                       │
                              │                                            │
                              │  ┌──────────┐  no JRE/JAR                  │
                              │  │ FALLBACK  │◄── (degraded UDP parsing)   │
                              │  └──────────┘                              │
                              └─────────────────────────────────────────────┘
```

### Backoff Schedule (crashes)

```
Crash #   Delay    Next State
──────    ─────    ──────────
  1        0s      → starting (immediate)
  2        2s      → starting
  3        —       → waiting_for_hardware (30s poll)
```

---

## 2. Scenario Flows

### A. Cold Start — No Hardware

```
TIME    JAVA BRIDGE              PYTHON BE                    REACT FE
────    ───────────              ─────────                    ────────

T=0     (not started)            manager.start() called       WS connecting...
        │                        status: stopped → starting   │
        │                        ▼ broadcast: bridge_status   │
        │                          {status:"starting"}        │
        │                                                     ▼
        │                                                     TopBar: ⚪ "Bridge starting..."
        │                                                     StartupIndicator: visible
        │                                                     StatusBanner: S4 (yellow, "Launching...")

T=1s    JAR spawned              subprocess launched           │
        WS server on :17400      WS client connects            │
        │                        status: starting → running    │
        │                        ▼ broadcast: bridge_status    │
        │                          {status:"running",          │
        │                           devices:{}, players:{}}    │
        │                                                      ▼
        │                                                      TopBar: 🟢 "Bridge: running"
        │                                                      TrafficDot: ⚫ (gray, no traffic)
        │                                                      StartupIndicator: hidden
        │                                                      StatusBanner: S2 (green,
        │                                                        "No Pioneer devices on en16.
        │                                                         Waiting for announcements.")
        │                                                      DeviceList: "No Pioneer devices
        │                                                        found. Check cable..."
        │                                                      PlayerList: "No active players."
        │                                                      DeckPanel: "Waiting for Deck N..."
        │                                                      HardwareTab: "No CDJ devices."

T=2s    heartbeat →              _last_message_time updated    │
                                 (not Pioneer, no traffic dot) │

T=2s    (repeats every 2s)       ▼ broadcast: pioneer_status   │
                                   {is_receiving: false,       │
                                    bridge_connected: true,    │
                                    last_message_age_ms: 1200} │
                                                               ▼
                                                               TrafficDot: ⚫ (gray, "none")

        ┌────────────────────────────────────────────────────────────────────┐
        │ STEADY STATE: Bridge healthy, no hardware. Waiting indefinitely.  │
        │ Health checks pass every 10s. Pioneer status every 2s.            │
        └────────────────────────────────────────────────────────────────────┘
```

### B. Hardware Plugged In (from steady state A)

```
TIME    JAVA BRIDGE              PYTHON BE                    REACT FE
────    ───────────              ─────────                    ────────

T=0     Pioneer announces        │                            │
        via Pro DJ Link          │                            │
        │                        │                            │
T=0.5s  ▼ emit: device_found    adapter._handle_device_found  │
          {device_name:"XDJ-AZ", _devices["169.254.1.3"]=dev  │
           device_number:3,      _last_pioneer_message_time ✓  │
           ip:"169.254.1.3",    ▼ broadcast: bridge_status     │
           uses_dlp:true}         {status:"running",           │
                                   devices:{"169.254.1.3":     │
                                     {name:"XDJ-AZ",...}}}     │
                                                               ▼
                                                               TopBar: 🟢 (unchanged)
                                                               TrafficDot: 🔵 cyan ping!
                                                               DeviceList: [XDJ-AZ #3]
                                                               HardwareTab: USB Browser enabled

T=1s    ▼ emit: player_status   adapter._handle_player_status  │
          {bpm:128, pitch:0,     _players[3] = PlayerState     │
           playback_state:       on_player_update() fires      │
           "playing",...}        ▼ broadcast: bridge_status     │
                                   {players:{"3":{bpm:128...}}} │
                                                                ▼
                                                                PlayerList: [Player 3: 128 BPM]
                                                                DeckPanel: resolving track...

T=2s    ▼ emit: track_metadata  adapter accumulates             │
        ▼ emit: beat_grid       on_track_loaded() fires         │
        ▼ emit: cue_points      ▼ broadcast: bridge_status      │
        ▼ emit: track_waveform                                   │
                                                                 ▼
                                                                 DeckPanel: waveform + metadata
                                                                 DeckWaveform: rendering

T=2s+   ▼ emit: beat (ongoing)  adapter.on_beat()               │
        (every beat ~469ms      tracker.update_position()        │
         at 128 BPM)            ▼ broadcast: bridge_status       │
                                  (player position updated)      │
                                                                 ▼
                                                                 DeckWaveform: cursor moving
                                                                 (rAF interpolation between
                                                                  WS updates)

        ┌────────────────────────────────────────────────────────────────────┐
        │ STEADY STATE: Bridge running, hardware active.                    │
        │ Beats flow ~2-4/sec. pioneer_status shows is_receiving:true.      │
        │ Position interpolated client-side between WS updates.             │
        └────────────────────────────────────────────────────────────────────┘
```

### C. Hardware Unplugged (from steady state B)

```
TIME    JAVA BRIDGE              PYTHON BE                    REACT FE
────    ───────────              ─────────                    ────────

T=0     USB cable removed        │                            │
        Link lost                │                            │
        │                        │                            │
T=0.5s  ▼ emit: device_lost     adapter._handle_device_lost   │
          {ip:"169.254.1.3"}     _devices.pop("169.254.1.3")  │
                                 on_device_change(dev,"lost")  │
                                 ▼ broadcast: bridge_status    │
                                   {status:"running",          │
                                    devices:{}, players:{...}} │
                                                               ▼
                                                               DeviceList: empty
                                                               (players may still show briefly)

T=1-5s  heartbeats continue     bridge still healthy           │
        (no Pioneer data)       _last_pioneer_message_time     │
                                 grows stale (>5s)             │
                                                               │
T=2s                             ▼ broadcast: pioneer_status   │
                                   {is_receiving: false,       │
                                    bridge_connected: true}    │
                                                               ▼
                                                               TrafficDot: ⚫ gray (no traffic)

T=8s                             │                             ▼
                                 │                             isHwDisconnected timer fires
                                 │                             StatusBanner: S8 (orange,
                                 │                               "Hardware Disconnected.
                                 │                                Reconnect a CDJ or DJM.")
                                 │                             PlayerList: S8 "Hardware
                                 │                               disconnected..."
                                 │                             DeckPanel: still shows last
                                 │                               known state (stale but not
                                 │                               cleared — player data persists
                                 │                               in bridge_status until cleared)

        ┌────────────────────────────────────────────────────────────────────┐
        │ STEADY STATE: Bridge running, hardware gone.                      │
        │ Status stays "running" — bridge is healthy, just no hardware.     │
        │ FE shows orange "Hardware Disconnected" banner after 8s grace.    │
        │ NO crash, NO restart. Waiting for hardware to return.             │
        └────────────────────────────────────────────────────────────────────┘
```

### D. Hardware Plugged Back In (from steady state C)

```
TIME    JAVA BRIDGE              PYTHON BE                    REACT FE
────    ───────────              ─────────                    ────────

T=0     Pioneer reappears        │                            StatusBanner: S8 (orange)
        │                        │                            │
T=0.5s  ▼ emit: device_found    adapter updates _devices      │
                                 _last_pioneer_message_time ✓  │
                                 ▼ broadcast: bridge_status    │
                                   {devices: populated}        │
                                                               ▼
                                                               isHwDisconnected → false
                                                               StatusBanner: S1 (green,
                                                                 "1 device on en16")
                                                               DeviceList: [XDJ-AZ #3]
                                                               TrafficDot: 🔵 cyan ping

T=1-2s  player_status, metadata  adapter repopulates           │
        beat_grid, waveforms     on_track_loaded() fires       │
                                 ▼ broadcasts                  │
                                                               ▼
                                                               PlayerList: populated
                                                               DeckPanel: track resolved

        ┌────────────────────────────────────────────────────────────────────┐
        │ Recovery: <2s. No bridge restart needed.                          │
        │ Seamless hardware re-discovery.                                   │
        └────────────────────────────────────────────────────────────────────┘
```

### E. Cold Start — Hardware Already Connected

```
TIME    JAVA BRIDGE              PYTHON BE                    REACT FE
────    ───────────              ─────────                    ────────

T=0     (not started)            manager.start()               WS connecting...
                                 status: stopped → starting    TopBar: ⚪ gray
                                                               StartupIndicator: "Connecting..."

T=1s    JAR spawns               WS connects                   │
        │                        status → running               │
        ▼ emit: bridge_status    adapter receives               │
        ▼ emit: device_found     _devices populated             ▼
        ▼ emit: device_found     _players populated             TopBar: 🟢 green
          (all devices at once)                                 TrafficDot: 🔵 cyan
                                 ▼ broadcast: bridge_status     DeviceList: populated
                                   {status:"running",           PlayerList: populating...
                                    devices:{...},
                                    players:{...}}

T=2-3s  metadata, beat_grid,    adapter accumulates             │
        waveforms, phrases      on_track_loaded() fires         │
                                ▼ broadcasts                    ▼
                                                                DeckPanel: waveform rendering
                                                                isRecovering: true (15s timer)
                                                                StatusBanner: S6 (green,
                                                                  "Discovering devices...")

T=16s   (steady state)          │                               isRecovering → false
                                                                StatusBanner: S1 (green,
                                                                  "2 devices on en16")

        ┌────────────────────────────────────────────────────────────────────┐
        │ Fastest path to full UI: ~3s. Recovery indicator for 15s.         │
        └────────────────────────────────────────────────────────────────────┘
```

### F. Bridge Crash — Single Recovery

```
TIME    JAVA BRIDGE              PYTHON BE                    REACT FE
────    ───────────              ─────────                    ────────

T=0     JVM crash / OOM          │                            │
        process exits            │                            │

T=10s   (dead)                   health_check detects:         │
                                  poll() returns exit code     │
                                 status: running → crashed     │
                                 adapter.clear()               │
                                   _devices={}, _players={}    │
                                 _consecutive_failures = 1     │
                                 delay = 0s (first crash)      │
                                 ▼ broadcast: bridge_status    │
                                   {status:"crashed",          │
                                    restart_attempt:1,         │
                                    devices:{}, players:{}}    │
                                                               ▼
                                                               TopBar: ⚪ gray "crashed"
                                                               StatusBanner: S3 (red,
                                                                 "Restart attempt 1/3.
                                                                  Restarting...")
                                                               PlayerList: S3 "Bridge crashed."
                                                               DeckPanel: "Bridge crashed."
                                                               devices/players cleared

T=10s   │                        immediate restart →           │
                                 status: crashed → starting    │
                                 ▼ broadcast                   │
                                                               ▼
                                                               StatusBanner: S4 (yellow)

T=11s   new JAR spawns           WS connects                   │
                                 status: starting → running    │
                                 _consecutive_failures = 0     │
                                   (prev uptime was >30s)      │
                                 ▼ broadcast                   │
                                                               ▼
                                                               TopBar: 🟢 green
                                                               isRecovering: true (15s)
                                                               StatusBanner: S6 (green,
                                                                 "Discovering devices...")

T=12s   device_found arrives     adapter repopulates           │
                                 ▼ broadcast                   │
                                                               ▼
                                                               DeviceList: populated
                                                               isRecovering → false (early)
                                                               StatusBanner: S1

        ┌────────────────────────────────────────────────────────────────────┐
        │ Total downtime: ~1-2s. FE briefly shows crashed, then recovers.  │
        └────────────────────────────────────────────────────────────────────┘
```

### G. Bridge Crash Threshold — 3 Rapid Crashes

```
TIME    JAVA BRIDGE              PYTHON BE                    REACT FE
────    ───────────              ─────────                    ────────

T=0     crash #1                 health_check detects          │
                                 failures=1, delay=0           │
                                 immediate restart             StatusBanner: S3 → S4 → S1

T=5s    crash #2 (<30s uptime)   health_check detects          │
                                 uptime <30s → no reset        │
                                 failures=2, delay=2s          │
                                 ▼ broadcast:                  │
                                   {status:"crashed",          │
                                    restart_attempt:2,         │
                                    next_retry_in_s:2.0}       │
                                                               ▼
                                                               StatusBanner: S3 (red,
                                                                 "Attempt 2/3. Retrying in 2s...
                                                                  If next fails, slow-poll mode.")
                                                               countdownSecondsRemaining: 2→1→0

T=7s    restart attempt #3       status → starting → running   │

T=10s   crash #3 (<30s uptime)   health_check detects          │
                                 failures=3 ≥ threshold        │
                                 ▼ ENTER waiting_for_hardware  │
                                   failures reset to 0         │
                                   start 30s poll loop         │
                                 ▼ broadcast:                  │
                                   {status:"waiting_for_       │
                                    hardware",                 │
                                    next_retry_in_s:30}        │
                                                               ▼
                                                               TopBar: 🟡 yellow "degraded"
                                                               StatusBanner: S5 (blue,
                                                                 "Crash threshold reached.
                                                                  Checking in 30s...")
                                                               countdownSecondsRemaining: 30→29→...

T=40s   (30s later)              poll: check interface exists   │
                                 if interface missing → skip   │
                                   ▼ broadcast: next_retry=30  │
                                                               ▼
                                                               countdown resets: 30→29→...
                                 if interface found → restart  │
                                   status → starting           │
                                                               ▼
                                                               StatusBanner: S4 (yellow)

        ┌────────────────────────────────────────────────────────────────────┐
        │ Slow-poll mode: tries every 30s. No focus-stealing.              │
        │ Separate from "fallback" (which is only for missing JRE/JAR).    │
        └────────────────────────────────────────────────────────────────────┘
```

### H. WebSocket Disconnect (FE → BE link drops)

```
TIME    JAVA BRIDGE              PYTHON BE                    REACT FE
────    ───────────              ─────────                    ────────

T=0     (unaffected)             (unaffected — bridge still    WS onClose fires
                                  running internally)          │
                                                               ▼
                                                               setWsConnected(false)
                                                               status → "not_initialized"
                                                               devices → {}
                                                               players → {}
                                                               isRecovering → false
                                                               countdownSecondsRemaining → null
                                                               all timers cleared

                                                               TopBar: ⚪ gray "disconnected"
                                                               StatusBanner: S7 (gray,
                                                                 "Backend Unreachable.
                                                                  Reconnecting...")
                                                               PlayerList: S7
                                                               DeckPanel: "ws-disconnected"
                                                               TrafficDot: hidden

T=1s    │                        │                             WS reconnect attempt #1
                                                               (backoff: 1s → 2s → 4s → 30s max)

T=1-2s  │                        │                             WS onOpen fires
                                                               setWsConnected(true)
                                                               resetMapperState()
                                                               prevBridgeStatus = null

                                 detects new client →          │
                                 sends current bridge_status   │
                                 sends pioneer_status          │
                                                               ▼
                                                               store receives bridge_status
                                                               status restored from payload
                                                               devices/players repopulated
                                                               TopBar: 🟢 (if running)
                                                               StatusBanner: restored
                                                               invalidates network queries

        ┌────────────────────────────────────────────────────────────────────┐
        │ FE-only event. Bridge/BE unaffected. FE recovers in 1-2s.        │
        │ All state rebuilt from first bridge_status message post-reconnect.│
        └────────────────────────────────────────────────────────────────────┘
```

### I. Board Power Off → Power On (Full Cycle)

```
TIME    JAVA BRIDGE              PYTHON BE                    REACT FE
────    ───────────              ─────────                    ────────

        ── POWER OFF ──

T=0     Pioneer broadcasts stop  │                            │
T=0.5s  ▼ emit: device_lost     adapter removes device        │
                                 ▼ broadcast                   ▼
                                                               DeviceList: empty
T=5s                             pioneer_traffic_active=false   TrafficDot: ⚫ gray
T=8s                             │                             isHwDisconnected: true
                                                               StatusBanner: S8 (orange,
                                                                 "Hardware Disconnected")

        ── STEADY STATE: Bridge running, no hardware ──
        ── (minutes, hours — bridge never crashes) ──

        ── POWER ON ──

T=N     Pioneer broadcasts start │                            │
T=N+0.5 ▼ emit: device_found    adapter adds device           │
                                 _last_pioneer_message_time ✓  │
                                 ▼ broadcast                   ▼
                                                               isHwDisconnected: false
                                                               StatusBanner: S1 (green)
                                                               DeviceList: populated
                                                               TrafficDot: 🔵 cyan

T=N+2   player_status, metadata  adapter accumulates           PlayerList: populated
                                 ▼ broadcasts                  DeckPanel: rendering

        ┌────────────────────────────────────────────────────────────────────┐
        │ Bridge NEVER crashes during power cycle. Clean device_lost/found. │
        │ FE shows orange "Hardware Disconnected" during gap.               │
        │ Recovery: <2s from power-on to full FE rendering.                 │
        └────────────────────────────────────────────────────────────────────┘
```

---

## 3. FE Component Truth Tables

### TopBar StatusDot

```
wsConnected  status                  dotStatus       color       tooltip
─────────── ──────────────────────  ──────────────  ──────────  ────────────────────────
false        *                       disconnected    ⚪ gray     "Backend unreachable"
true         not_initialized         disconnected    ⚪ gray     "Not initialized"
true         stopped                 disconnected    ⚪ gray     "Bridge: stopped"
true         starting                disconnected    ⚪ gray     "Bridge: starting"
true         crashed                 disconnected    ⚪ gray     "Crashed — restarting in Ns"
true         no_jre                  disconnected    ⚪ gray     "Java not found"
true         no_jar                  disconnected    ⚪ gray     "Bridge JAR missing"
true         running                 connected       🟢 green   "Bridge: running"
true         fallback                degraded        🟡 yellow  "Fallback mode"
true         waiting_for_hardware    degraded        🟡 yellow  "Waiting for hardware"
```

### TopBar TrafficDot

```
dotStatus       isReceiving  isRecovering  status                 render
──────────────  ───────────  ────────────  ─────────────────────  ──────────────────────
disconnected    *            *             *                       HIDDEN
connected       true         *             *                       🔵 cyan + ping ripple
connected       false        true          *                       ⚫ gray + pulse anim
connected       false        false         *                       ⚫ gray (static)
degraded        *            *             waiting_for_hardware    ⚫ gray (static)
degraded        true         *             fallback                🔵 cyan + ping
degraded        false        *             fallback                ⚫ gray (static)
```

### StatusBanner Priority

```
PRIORITY  CONDITION                                          BANNER
────────  ─────────────────────────────────────────────────  ──────────────────────────
1 (S7)    !wsConnected                                       ⚫ "Backend Unreachable"
2 (S8)    isHwDisconnected                                   🟠 "Hardware Disconnected"
3 (S6)    status=running + isRecovering                      🟢 "Discovering devices..."
4 (S1)    status=running + devices.length > 0                🟢 "N devices on interface"
5 (S2)    status=running + devices.length === 0              🟢 "No devices. Waiting..."
6 (S3)    status=crashed                                     🔴 "Attempt N/3. Retrying..."
7 (S4)    status=starting                                    🟡 "Launching bridge..."
8 (S5)    status=waiting_for_hardware                        🔵 "Checking in Ns..."
9         status=no_jre/no_jar/stopped/fallback              config-driven
```

### DeckPanel Empty States

```
PRIORITY  CONDITION                             KIND              MESSAGE
────────  ────────────────────────────────────  ────────────────  ─────────────────────────
1         bridgeOverride set                    varies            Bridge-level message
  1a        !wsConnected                        ws-disconnected   "Backend unreachable"
  1b        status=crashed                      bridge-crashed    "Bridge crashed."
  1c        status=starting                     bridge-starting   "Bridge starting..."
  1d        status=waiting_for_hardware         waiting-hardware  "Waiting for hardware..."
2         !player data                          no-player         "Waiting for Deck N data..."
3         rekordbox_id === 0                    no-track          "No track loaded on Deck N"
4         resolve loading                       resolving         "Resolving track..."
5         resolve error + no Pioneer wf         not-found         (diagnostic table + retry)
5'        resolve error + Pioneer wf exists     —                 Pioneer waveform fallback
6         analysis loading                      loading-analysis  "Loading analysis..."
7         no waveform + no Pioneer wf           no-waveform       "Re-analyze with waveform"
7'        no waveform + Pioneer wf exists       —                 Pioneer waveform fallback
8         waveform exists                       —                 Full rendering
```

### HardwareTab Gating

```
isStartingUp  status      cdjDevices.length  RENDERS
────────────  ──────────  ─────────────────  ────────────────────────────
true          *           *                  "Connecting..."
false         ≠ running   *                  "Bridge is not connected."
false         running     0                  "No CDJ devices detected."
false         running     > 0                Full UI (browser + controls)
```

---

## 4. Key Timing Reference

```
INTERVAL          VALUE     PURPOSE
────────────────  ────────  ────────────────────────────────────
Health check       10s      Check subprocess alive + WS silence
WS silence crash   20s      No messages → crash (2× health_check)
Pioneer timeout     5s      is_receiving goes false
FE traffic grace    8s      isHwDisconnected activates
FE recovery timer  15s      isRecovering active after status→running
Restart backoff    0/2/4/   Exponential, capped at 30s
                   8/16/30s
Crash threshold     3       Crashes before waiting_for_hardware
Stable uptime      30s      Must run 30s to reset failure counter
HW poll interval   30s      Polling rate in waiting_for_hardware
WS reconnect       1s→30s   FE WebSocket reconnection backoff
Pioneer status     2s       Backend → FE heartbeat interval
```
