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

### rbox ANLZ parser panics on XDJ-AZ exported files
Date: 2026-03-16
Milestone: M-0B
Symptom: `rbox.Anlz()` constructor causes Rust panic (process abort) when opening certain ANLZ0000.DAT files from XDJ-AZ USB exports. The panic occurs during ANLZ section parsing with "no variants matched" and "assertion failed" errors in the BeatGrid parser.
Root cause: rbox v0.1.7's Rust ANLZ parser doesn't handle all ANLZ section variants exported by the XDJ-AZ. The parser encounters unknown section tags at certain file offsets and panics instead of returning an error.
Fix: Replaced rbox ANLZ parsing with two-tier pure-Python strategy (ADR-013): pyrekordbox (primary) + custom anlz_parser.py (fallback). rbox retained for exportLibrary.db reading only. ANLZ reading re-enabled.
File(s): scue/layer1/usb_scanner.py, scue/layer1/anlz_parser.py, pyproject.toml
