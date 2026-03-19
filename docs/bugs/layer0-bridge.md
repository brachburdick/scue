# Bug Log — Layer 0 (Beat-Link Bridge)

Append-only log of bugs found and fixed in the bridge layer (Java subprocess, WebSocket, Python adapter).
Record every fix, no matter how small — patterns emerge over time.

**Format:**
```
### Short title
Date: YYYY-MM-DD
Milestone: M-X (or N/A)
Symptom: What did the user see or what broke?
Root cause: Why did it happen?
Fix: What was changed and where?
File(s): path/to/file.py
```

---

### MetadataFinder returns wrong track titles on XDJ-AZ
Date: 2026-03-16
Milestone: M-0
Symptom: Track metadata (title, artist) shown by bridge was incorrect. First load per player was correct, subsequent loads showed metadata for wrong tracks. BPM was always correct.
Root cause: XDJ-AZ uses Device Library Plus (DLP) format with different track ID namespace than legacy export.pdb. beat-link's MetadataFinder used DLP IDs to query DeviceSQL data, returning wrong records. Additionally, CdjStatus.getRekordboxId() changes value for the same track between paused and playing states on the XDJ-AZ, making ID-based track change detection unreliable.
Fix: Stripped MetadataFinder, BeatGridFinder, WaveformFinder, CrateDigger, and AnalysisTagFinder from the bridge JAR (ADR-012). Bridge now provides real-time playback data only. Metadata resolution moved to Python side via rbox library reading directly from USB's exportLibrary.db. Updated adapter to fire on_track_loaded from rekordbox_id changes in player_status. Updated status endpoint to include uses_dlp flag per device.
File(s): bridge-java/src/main/java/com/scue/bridge/BeatLinkBridge.java, bridge-java/src/main/java/com/scue/bridge/MessageEmitter.java, scue/bridge/adapter.py, scue/bridge/messages.py, scue/bridge/manager.py

### fix_route() reports failure after successful route add on macOS
Date: 2026-03-17
Milestone: M-0 (route automation)
Symptom: POST `/api/network/route/fix` returned HTTP 500 with "Route fix ran but route still points to None" even though `sudo scue-route-fix en16` exited 0 and printed "Route fixed: 169.254.255.255 -> en16".
Root cause: `fix_route()` verified the fix with `route get 169.254.255.255` immediately after the script ran. On macOS, `route get` for link-local broadcast addresses does not reliably reflect a just-added host route — it falls back to the connected subnet route and often omits the `interface:` line entirely. The fix had actually succeeded at the kernel level, but the verification produced a false negative. Additionally, `netstat -rn` is a more authoritative source than `route get` for checking whether a specific host route exists.
Fix: (1) Removed the hard-fail on post-fix verification in `fix_route()`. Script exit 0 is now the source of truth for success; `route get` discrepancies are logged at DEBUG level only. (2) Rewrote `get_current_route()` to prefer `netstat -rn -f inet` (checks the actual kernel routing table for an exact `169.254.255.255` host-route entry) and fall back to `route get` only if no netstat match is found.
File(s): scue/network/route.py

### check_sudoers_installed() always returns False despite sudoers being present
Date: 2026-03-17
Milestone: M-0 (route automation)
Symptom: RouteStatusBanner showed "Route fix not available. Run: sudo ./tools/install-route-fix.sh" even after the user had successfully run the installer. The "Fix Now" button never appeared.
Root cause: `check_sudoers_installed()` ran `sudo -n /usr/local/bin/scue-route-fix --check`. The installed script handled `--check` AFTER the `^en[0-9]+$` interface validation regex, so `--check` failed the regex and the script exited 1 before reaching the check handler. `sudo -n` propagated the exit code; Python saw rc=1 and returned False. Sudoers was correctly installed but detected as missing.
Fix: (1) Rewrote `check_sudoers_installed()` to use file presence (`os.path.isfile` for both `/usr/local/bin/scue-route-fix` and `/etc/sudoers.d/scue-djlink`) instead of a subprocess call — more reliable and faster. (2) Fixed argument ordering in `install-route-fix.sh` so the generated script handles `--check` before the regex validation for future installs.
File(s): scue/network/route.py, tools/install-route-fix.sh

### macOS link-local broadcast routing goes to wrong interface
Date: 2026-03-16 (updated 2026-03-17)
Milestone: M-0
Symptom: Bridge connected but immediately cycled between device_found/device_lost. VirtualCdj threw NoRouteToHostException when sending announcement packets. On v1.2.0 with `--interface` flag, bridge runs but `devices: {}` because beat-link probes go out the wrong interface.
Root cause: macOS assigns the 169.254.255.255 broadcast route to whichever link-local interface registers first (usually en0/Wi-Fi). When Pioneer hardware is on Ethernet (en16), broadcast packets go out the wrong interface. beat-link 8.0.0 has NO API to force a specific network interface — VirtualCdj.start() auto-discovers by probing, so the OS route must be correct. Breaks on reboot, cable unplug/replug, or adapter change.
Fix: (1) `sudo ./tools/fix-djlink-route.sh en16` fixes the route. (2) Java bridge v1.2.0 checks the route on startup and emits a warning with the fix command if wrong. (3) Python BridgeManager also checks and logs a warning before launching subprocess.
File(s): bridge-java/src/main/java/com/scue/bridge/BeatLinkBridge.java, scue/bridge/manager.py, tools/fix-djlink-route.sh

### Nonsensical pitch value when no track is loaded
Date: 2026-03-17
Milestone: M-0
Symptom: Player status shows `pitch: -6.95` (or similar garbage) when no track is loaded on a deck.
Root cause: `CdjStatus.getPitch()` returns a raw hardware value even when `trackType == NO_TRACK`. The BPM was already guarded with a NO_TRACK check but pitch was not.
Fix: Apply the same `noTrack ? 0.0 : ...` guard to pitch calculation, matching the existing BPM guard.
File(s): bridge-java/src/main/java/com/scue/bridge/BeatLinkBridge.java

### [FIXED] Pioneer traffic detected but device never "discovered" by beat-link
Date: 2026-03-17
Milestone: M-0
Symptom: Bridge reports Pioneer traffic on en16 (traffic indicator fires, `isReceiving=true`) but `devices` remains empty — beat-link never emits a device_found event.
Root cause: Two compounding issues:
1. **`is_receiving` was inflated by bridge heartbeats.** `pioneer_status.is_receiving` was derived from `_last_message_time` which was updated by ALL WebSocket messages from the Java bridge, including `bridge_status` heartbeats. When VirtualCdj.start() failed repeatedly (due to route issues), the bridge's error-recovery `bridge_status` emissions kept `is_receiving` flickering to `true`, misleading the frontend into showing "Pioneer traffic detected" when no Pioneer hardware data was actually arriving.
2. **Listen loop crash left bridge in zombie state.** When the WebSocket listen loop encountered an error, it set `_status = "crashed"` but did NOT trigger `_schedule_restart()`. The health check loop saw the non-"running" status and exited without restarting. The Java subprocess kept running (zombie) but its WebSocket server died, leaving the Python side permanently stuck in "crashed" state with `restart_count: 1`.
Fix:
1. Split message tracking into `_last_message_time` (all messages, for bridge liveness) and `_last_pioneer_message_time` (only device_found/player_status/beat/etc., for Pioneer traffic). Updated `ws.py` to use `_last_pioneer_message_time` for `is_receiving` and added `bridge_connected` field to `pioneer_status` WS message.
2. Added `await self._schedule_restart()` to the listen loop error handler so the bridge auto-recovers from WebSocket disconnections.
File(s): scue/bridge/manager.py, scue/api/ws.py

Remaining open questions:
- Is there a way to maintain device state in the UI when we temporarily stop receiving Pioneer traffic (e.g. deck paused, USB unplugged briefly)? Losing all device info on a momentary gap seems fragile for live use.

### Devices empty despite active player_status messages
Date: 2026-03-17
Milestone: M-0
Symptom: Bridge status shows `devices: {}` even though `player_status` and `beat` messages are actively streaming from hardware. Bridge page shows "DEVICES (0)" but "PLAYERS (2)" with live BPM/pitch data. The `device_found` event was never received by the Python adapter.
Root cause: The Java bridge emits `device_found` once per device when it first discovers them. These events fire during `initBeatLink()` before the Python WebSocket client connects. The `BridgeWebSocketServer.onOpen()` does not replay current device state to newly connected clients. When the Python side reconnects (or connects after a delay), it misses the initial `device_found` events permanently.
Fix: Added `_ensure_device_from_player()` to `BridgeAdapter`. When `player_status` messages arrive for a player number that has no corresponding device entry, a synthetic `DeviceInfo` is created and `on_device_change` is fired. This ensures the `devices` dict stays populated even if `device_found` was missed. The XDJ-AZ got a real `device_found` (it was rediscovered after restart) while Player 1 was inferred from `player_status`. Future improvement: add state replay to the Java bridge's `BridgeWebSocketServer.onOpen()` so real device info (name, IP) is sent on connect.
File(s): scue/bridge/adapter.py

### [FIXED] Bridge crash-restart cycle after hardware disconnect/reconnect
Date: 2026-03-18
Fixed: 2026-03-18
Milestone: M-0
Priority: HIGH
Status: FIXED — see fix details at bottom of this entry.

**Summary:**
When Pioneer hardware connectivity is disrupted (USB-Ethernet adapter yanked, board powered off) and then restored, the bridge enters an unrecoverable crash-restart cycle. The Java subprocess repeatedly starts, fails, and restarts — each restart steals macOS window focus briefly (app name "beat link trigger" flashes in menu bar). Only a full server restart resolves the cycle.

**Reproduction scenarios (all tested manually 2026-03-18):**

**Scenario 1 — Yank USB-Ethernet adapter while connected:**
- Observed: Pioneer traffic ceases immediately (correct). Hardware selection panel stays "connected" initially (stale — should update). Eventually bridge crashes. When crash happens: XDJ disappears from device list but Player 2 remains; Players 1 & 2 retain last statuses (stale). Crash-restart cycle begins.
- After plugging adapter back in: Hardware selection fixes itself, but Pioneer traffic indicator does NOT update to reflect restored traffic. Crash-restart cycle continues. Each cycle shows "bridge starting..." indicator and steals OS focus. Page reload + "Apply and Restart Bridge" does NOT break the cycle. Only full server restart resolves.

**Scenario 2 — Restart server with USB-Ethernet unplugged:**
- Observed: Shows "Route mismatch: 169.254.255.255 → none (should be en16)" with "Fix Now" button. Fix fails: `API 500: {"detail":{"success":false,"error":"route: bad address: en16","previous_interface":null,"new_interface":"en16"}}`. Initially no crash cycle (good), but after some time the bridge crashes and the cycle starts again.

**Scenario 3 — Power off board while connection is good:**
- Observed: Pioneer traffic ceases (correct). No other changes in devices, players, or hardware selection (all stale — should update). Clicking "Apply and Restart Bridge" while board is off triggers the crash-restart cycle.
- Recovery: Powering board back on eventually restores connection and breaks the cycle, but takes noticeably long. When it does reconnect, Player 1 appeared under devices (first time — previously only Player 2 was shown).

**Scenario 4 — Apply and Restart Bridge while fully connected:**
- Observed: Works perfectly — no issues.

**Additional observations:**
- "beat link trigger" app name flashes in macOS menu bar during each restart cycle. The bridge JAR's Main-Class is `com.scue.bridge.BeatLinkBridge` — the name likely comes from beat-link library's internal AWT/Swing initialization. Each Java subprocess launch briefly steals OS focus.
- Player 1 is intermittently missing from device list on initial load. Player 2 shows as "inferred" (from `_ensure_device_from_player()`). This may be a timing issue with `device_found` event delivery — see existing bug "Devices empty despite active player_status messages" above.
- Route fix API returns 500 with "route: bad address: en16" when the interface doesn't exist (adapter unplugged). Error message should be user-friendly.

---

**Expected behavior per scenario (acceptance criteria for fix):**

**AC-1: Graceful hardware disconnect (adapter yank or board power-off):**
- Pioneer traffic indicator → off within 2-3 seconds
- Device list → clears or shows "disconnected" state (not stale data)
- Player list → shows "offline" or clears (not stale last-known data)
- Hardware selection → updates to reflect lost interface
- Bridge status → "degraded" or "waiting for hardware", NOT crash-restart cycle
- No OS focus stealing

**AC-2: Hardware reconnect after disconnect:**
- Bridge should detect restored connectivity and recover WITHOUT crash-restart cycle
- Pioneer traffic indicator → on within 5 seconds of traffic resuming
- Devices and players → repopulate within 5 seconds
- NO user intervention required (no page reload, no "Apply and Restart")

**AC-3: Bridge restart without hardware present:**
- Bridge starts, detects no hardware, enters a stable "waiting" state
- Route fix API returns a clear user-facing error when interface doesn't exist (not raw "route: bad address")
- No crash-restart cycle — bridge waits patiently for hardware to appear
- When hardware appears later, bridge picks it up automatically

**AC-4: OS focus behavior:**
- Java subprocess launch MUST NOT steal macOS window focus
- Investigate: can `-Djava.awt.headless=true` be passed to suppress AWT initialization?
- If beat-link requires AWT, investigate `-Dapple.awt.UIElement=true` (hides from Dock/Cmd-Tab)

**AC-5: "beat link trigger" app name:**
- The Java process should identify as "SCUE Bridge" or similar, not "beat link trigger"
- Investigate: `-Xdock:name="SCUE Bridge"` JVM flag or setting `apple.laf.useScreenMenuBar`

---

**Root cause hypotheses (for investigation):**
1. **No circuit breaker on restart when hardware is absent:** `_schedule_restart()` has exponential backoff and a `max_crash_before_fallback` (3 crashes → fallback mode). But if the bridge KEEPS crashing after fallback, or if fallback itself crashes, there's no stable terminal state. The bridge may be oscillating between "try to start" → "no interface/route" → "crash" → "restart" indefinitely.
2. **Health check triggers restart on silence:** Lines 354-361 of `manager.py` restart the bridge if it's been silent for `2 × health_check_interval`. When hardware is disconnected, the bridge may go silent (no Pioneer traffic) → health check fires → restart → still no hardware → silent again → loop.
3. **`_consecutive_failures` may reset on partial success:** If the bridge process starts successfully (WebSocket connects) but then crashes shortly after, `_consecutive_failures` might reset — preventing fallback mode from ever triggering.
4. **Java AWT thread keeps process alive in bad state:** beat-link creates AWT threads for virtual CDJ. If VirtualCdj.start() fails (no route/no interface), the AWT thread may linger, causing the process to not exit cleanly, confusing the Python-side lifecycle management.

**Fix (2026-03-18, updated after QA live hardware session):**

Six root causes confirmed and fixed:

**1. Health check silenced Pioneer traffic as restart trigger.**
`_health_check_loop` was restarting the bridge when `_last_message_time` was silent for `2 × health_check_interval`. Since `_last_message_time` is updated by ALL bridge messages (including heartbeats), the bridge would only go silent if the Java process itself died or the WebSocket dropped — not when hardware was disconnected. However, the silence check was semantically wrong: it was designed to catch "bridge went quiet" but would fire if the Java bridge itself crashed and stopped heartbeating, then the health check would restart while `_schedule_restart()` was also running, leading to duplicate restarts. Fixed by clarifying the comment and rename to "bridge WebSocket heartbeat silence" check. Pioneer silence (`_last_pioneer_message_time`) is explicitly NOT a restart trigger.

**2. `_consecutive_failures` reset on brief start-then-crash cycles.**
When the bridge briefly reached "running" state (Java started, WS connected) but then crashed quickly (VirtualCdj.start() fails because no hardware/route), `start()` reset `_consecutive_failures = 0`. This prevented fallback from triggering even if the bridge crashed every few seconds. Fixed by tracking `_last_stable_start_time` and only resetting `_consecutive_failures` when the previous run lasted ≥ `_MIN_STABLE_UPTIME_S` (30 seconds).

**3. No stable terminal state after crash threshold.**
After `max_crash_before_fallback` crashes, the bridge entered "fallback" (UDP parser) mode. But the "fallback" state is for when JRE/JAR is absent — it's wrong for hardware-absent scenarios. The UDP fallback has no retry path back to full bridge mode. Fixed by adding a new `"waiting_for_hardware"` state: instead of starting the UDP fallback parser, the bridge enters a slow-poll loop (every 30 s) that calls `start()` to check if hardware has returned. `_consecutive_failures` is reset to 0 on entry so the next cycle starts fresh. Fallback (UDP parser) is now only entered when JRE or JAR is absent.

**4. JVM flags missing — AWT caused focus stealing and "beat link trigger" app name.**
The Java subprocess was launched without headless/UIElement JVM flags, causing macOS AWT to initialize and steal window focus on every launch. Fixed by adding `_JVM_FLAGS` constant to `manager.py` containing:
- `-Djava.awt.headless=true` — prevents AWT display connection
- `-Dapple.awt.UIElement=true` — hides process from Dock/Cmd-Tab
- `-Xdock:name=SCUE Bridge` — sets app name in any residual AWT menu entry

**5. Route fix error message was raw kernel output.**
`fix_route()` in `manager.py` returned the raw kernel error "route: bad address: en16" when the interface doesn't exist (adapter unplugged). Fixed by wrapping "bad address" errors with a user-readable message explaining that the USB-Ethernet adapter must be connected.
Note: QA live testing (2026-03-18) confirmed this wrapping was applied to `manager.py` only.
`scue/api/network.py:fix_route_endpoint()` bypassed the manager and returned the raw error.
**Fixed (2026-03-18):** Applied the same "bad address" / "no such interface" wrapping in
`fix_route_endpoint()` (`scue/api/network.py:116–135`). Regression tests added in
`tests/test_api/test_bridge_api.py::TestRouteFixFriendlyError`.

**6. `_last_message_time` not reset in `start()` — drives crash cycle on all restarts. [FIXED]**
Identified by QA live hardware testing (2026-03-18). `start()` did not reset `_last_message_time`
to `0.0` before launching the subprocess. After any crash, `_last_message_time` held the
timestamp from the previous run. The health check guard (`if self._last_message_time > 0`)
evaluated True, and the health check fired within 10s of restart — before beat-link had time
to connect — driving another crash. This is why SC-001/SC-003/SC-004/SC-010 failed with
crash-restart cycles despite fixes 1–5. SC-005 (cold start) passed because at process start
`_last_message_time = 0.0` (class default), so the guard evaluated False and health check
never fired.
Fixed (2026-03-18): added `self._last_message_time = 0.0` at line 160 of `start()`, before
status transition and `_launch_subprocess()`. Regression test added:
`tests/test_bridge/test_manager.py::TestLastMessageTimeReset`.

File(s): scue/bridge/manager.py, tests/test_bridge/test_manager.py

---

### rbox ANLZ parser panics on XDJ-AZ exported files
Date: 2026-03-16
Milestone: M-0B
Symptom: `rbox.Anlz()` constructor causes Rust panic (process abort) when opening certain ANLZ0000.DAT files from XDJ-AZ USB exports. The panic occurs during ANLZ section parsing with "no variants matched" and "assertion failed" errors in the BeatGrid parser.
Root cause: rbox v0.1.7's Rust ANLZ parser doesn't handle all ANLZ section variants exported by the XDJ-AZ. The parser encounters unknown section tags at certain file offsets and panics instead of returning an error.
Fix: Replaced rbox ANLZ parsing with two-tier pure-Python strategy (ADR-013): pyrekordbox (primary) + custom anlz_parser.py (fallback). rbox retained for exportLibrary.db reading only. ANLZ reading re-enabled.
File(s): scue/layer1/usb_scanner.py, scue/layer1/anlz_parser.py, pyproject.toml
