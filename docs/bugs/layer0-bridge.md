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

### rbox ANLZ parser panics on XDJ-AZ exported files
Date: 2026-03-16
Milestone: M-0B
Symptom: `rbox.Anlz()` constructor causes Rust panic (process abort) when opening certain ANLZ0000.DAT files from XDJ-AZ USB exports. The panic occurs during ANLZ section parsing with "no variants matched" and "assertion failed" errors in the BeatGrid parser.
Root cause: rbox v0.1.7's Rust ANLZ parser doesn't handle all ANLZ section variants exported by the XDJ-AZ. The parser encounters unknown section tags at certain file offsets and panics instead of returning an error.
Fix: Replaced rbox ANLZ parsing with two-tier pure-Python strategy (ADR-013): pyrekordbox (primary) + custom anlz_parser.py (fallback). rbox retained for exportLibrary.db reading only. ANLZ reading re-enabled.
File(s): scue/layer1/usb_scanner.py, scue/layer1/anlz_parser.py, pyproject.toml
