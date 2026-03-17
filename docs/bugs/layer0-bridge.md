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
Date: 2026-03-16
Milestone: M-0
Symptom: Bridge connected but immediately cycled between device_found/device_lost. VirtualCdj threw NoRouteToHostException when sending announcement packets.
Root cause: macOS assigns the 169.254.255.255 broadcast route to whichever link-local interface registers first (usually en0/Wi-Fi). When Pioneer hardware is on Ethernet (en16), broadcast packets go out the wrong interface. Breaks on reboot, cable unplug/replug, or adapter change.
Fix: Manual route fix: `sudo route delete 169.254.255.255 && sudo route add -host 169.254.255.255 -interface en16`. Needs automation via startup script.
File(s): N/A (OS-level routing)
