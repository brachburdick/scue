# Learnings

Append-only log of non-obvious discoveries, bugs, and corrections.
When something bites you, add it here so the next session doesn't repeat the mistake.

**Format:**
```
### Short title
Date: YYYY-MM-DD
Context: What were you doing?
Problem: What went wrong or was surprising?
Fix/Pattern: What's the correct approach?
Prevention: How to avoid in the future?
```

---

## Layer 0 — Beat-Link Bridge

### beat-link MetadataFinder returns wrong metadata on XDJ-AZ (and all Device Library Plus hardware)
Date: 2026-03-16
Context: Building the Java bridge JAR. Testing with Pioneer XDJ-AZ all-in-one DJ unit.
Problem: Track metadata (title, artist) from MetadataFinder is incorrect after the first track load per player. BPM from CdjStatus is always correct. The XDJ-AZ uses Device Library Plus (DLP) format (`exportLibrary.db`) with a different ID namespace than legacy `export.pdb`. When MetadataFinder uses the DLP ID to query CrateDigger's DeviceSQL data, it retrieves the wrong record. Confirmed known issue: beat-link-trigger's CHANGELOG states the XDJ-AZ always uses Device Library Plus IDs.
Fix: Use the `rbox` Python library to read metadata directly from the USB's `exportLibrary.db`, bypassing beat-link's metadata system entirely. Use beat-link only for real-time playback data (BPM, pitch, beat position, on-air, beat events). See ADR-012 in DECISIONS.md.
Prevention: Any time new Pioneer hardware is supported, check whether it uses DLP or legacy DeviceSQL. Affected hardware: XDJ-AZ, Opus Quad, OMNIS-DUO, CDJ-3000X.

### XDJ-AZ track change detection: trackType does NOT transition through NO_TRACK
Date: 2026-03-16
Context: Same debugging session as above.
Problem: When a new track is loaded on the same deck of the XDJ-AZ, `CdjStatus.getTrackType()` stays as `REKORDBOX` — it never passes through `NO_TRACK`. Track-change detection watching for `NO_TRACK → REKORDBOX` transitions never fires.
Fix: Detect track changes by monitoring `CdjStatus.getRekordboxId()` for value changes (even though the ID is unreliable for metadata lookup, a change in ID reliably indicates a new track was loaded). Use multiple signals: rekordbox ID change OR trackType transition OR significant BPM change at same pitch.
Prevention: All track-change detection in the bridge should use multiple signals rather than depending on any single signal.

### beat-link binds to wrong network interface on macOS
Date: 2026-03-16 (updated 2026-03-17)
Context: Building the Java bridge JAR. beat-link auto-detection picked the wrong network interface.
Problem: macOS has many interfaces (Wi-Fi, Thunderbolt bridge, VPN, Docker, AWDL, etc.). beat-link's default interface discovery may pick any of them. When it picks the wrong one, it silently connects to nothing — no error, no timeout, just no devices discovered. **Critical: beat-link 8.0.0 has NO API to force a specific network interface.** `VirtualCdj.start()` auto-discovers by sending probes to devices found by DeviceFinder. On macOS, the link-local broadcast route (169.254.255.255) must point to the correct interface or probes go nowhere.
Fix: (1) Fix macOS route before starting bridge: `sudo ./tools/fix-djlink-route.sh en16`. (2) The bridge v1.2.0 checks the route on startup and emits a warning if wrong. (3) Python BridgeManager also checks and logs. (4) Bridge still does scored auto-detection and `--interface` CLI override for interface selection/logging, but the actual binding is beat-link's responsibility (driven by correct OS routing).
Prevention: Always fix the macOS route after reboot/cable change. The route does not persist across reboots. Always log which interface was selected and why. Surface the interface list and selection in the bridge_status message so the UI can display it.

### macOS broadcast UDP reception — IP_BOUND_IF required
Date: 2025-03
Context: Connecting Pioneer XDJ-AZ via CAT-5 on en16 (169.254.20.47). Sockets binding correctly but packet_count stayed at 0.
Problem: On macOS, a UDP socket bound to a unicast IP (e.g. 169.254.20.47) does NOT receive broadcast packets from that interface. The kernel drops them silently. This affects any Pioneer hardware, which broadcasts keepalives and status packets.
Fix: Bind to `""` (INADDR_ANY / 0.0.0.0) and use `setsockopt(IPPROTO_IP, IP_BOUND_IF=25, socket.if_nametoindex(iface_name))` to lock the socket to the specific interface.
Prevention: Always use IP_BOUND_IF on macOS for any interface-specific UDP listener. Never bind to a unicast IP if you expect to receive broadcasts.

---

## Layer 1 — Track Analysis & Live Tracking

### allin1 vs allin1_mlx import name
Date: 2025-03
Context: Setting up Apple Silicon ML analysis.
Problem: The package installed as `all-in-one-mlx` via pip but must be imported as `allin1_mlx`, not `allin1`. Using `import allin1` raises ImportError.
Fix: `import allin1_mlx` and `allin1_mlx.analyze(path)`.
Prevention: Double-check import name vs. package name for MLX forks.

### allin1-mlx requires pre-converted MLX weights in mlx-weights/
Date: 2026-03-16
Context: First run of allin1-mlx after pip install all-in-one-mlx.
Problem: FileNotFoundError for harmonix-fold0_mlx.safetensors. The package does NOT auto-download weights — it expects pre-converted MLX .npz or .safetensors files in a local `mlx-weights/` directory (default CWD-relative).
Fix: Copy weights from POC's `mlx-weights/` directory to project root `mlx-weights/`. Pass `mlx_weights_dir=` kwarg explicitly via `_find_weights_dir()` that searches upward from the package.
Prevention: Always verify weight file availability before first analysis run. The mlx-weights/ dir is gitignored (binary). Document weight setup in onboarding.

### librosa beat tracking drifts on tempo-variable tracks
Date: 2025-03
Context: Analyzing progressive house tracks with gradual BPM shift.
Problem: librosa.beat.beat_track assumes constant tempo. Beats can drift by ~200ms over 5 minutes.
Fix: Use librosa beat tracking as the working reference only. After Pioneer enrichment pass, replace the librosa beatgrid with Pioneer's hand-verified rekordbox grid.
Prevention: Never rely solely on librosa beat grid for production timing. Always plan for Pioneer enrichment.

### Section boundaries must be clamped to track start/end
Date: 2026-03-16
Context: Running analysis pipeline on real tracks with librosa-only fallback (no allin1-mlx).
Problem: Ruptures change-point detection can place the first boundary at 1–2s into the track, leaving no coverage of the opening. Similarly, the last boundary may not reach the track end.
Fix: After all snapping and scoring, clamp: first section.start = 0.0, last section.end = track duration.
Prevention: Always post-process section lists to ensure full track coverage.

### ruptures KernelCPD needs 4x downsample for performance
Date: 2026-03-16
Context: Running ruptures on full feature matrix (22 dimensions, ~1900 frames for a 3-min track).
Problem: KernelCPD is O(n²). Without downsampling, analysis takes 30+ seconds per track.
Fix: Downsample by 4x before feeding to ruptures. Boundary timestamps converted back at original resolution. No meaningful loss of precision for section-level boundaries.
Prevention: Always downsample for ruptures. Adjust min_size accordingly.

### bar counting is downbeat counting, not interval counting
Date: 2026-03-16
Context: Writing _count_bars for 8-bar snap pass.
Problem: Counting bars by counting downbeats in a range counts the START markers, not intervals. A range from bar 0 to bar 8 has 9 downbeats (0,1,2,...8) but 8 bars.
Fix: The implementation counts downbeats within [start, end) using a half-open interval. Tests must match this semantic. Include an extra downbeat at the end of the track's downbeat list.
Prevention: Be explicit about whether counting markers or intervals. Document the half-open interval convention.

### rbox Rust ANLZ parser panics on DLP ANLZ files — replaced with pure Python
Date: 2026-03-17
Context: USB scanning with rbox v0.1.7 on XDJ-AZ ANLZ files.
Problem: `rbox.Anlz()` causes a Rust `panic!()` on certain ANLZ files from XDJ-AZ USB exports. The panic aborts the entire Python process — it's uncatchable. The Rust parser hits unknown section variants in DLP-format ANLZ files and panics instead of returning an error. Not all files fail, but the risk is unpredictable.
Fix/Pattern: Two-tier pure-Python ANLZ parsing (ADR-013): Tier 1: pyrekordbox `AnlzFile.parse_file()`. Tier 2: custom `anlz_parser.py` (zero deps, beat grid + cues only). Both are pure Python — exceptions, not panics. rbox kept for `exportLibrary.db` reading only.
Prevention: Never use Rust-backed parsers for untrusted binary formats without subprocess isolation. Pure Python is slower but cannot abort the process. If a Rust library must be used, wrap it in a subprocess.

---

## Layer 2 — Cue Generation

*(No entries yet)*

---

## Layer 3 — Effect Engine

*(No entries yet)*

---

## Layer 4 — Output & Hardware

*(No entries yet)*

---

## UI / WebSocket

### pioneer_status WebSocket message needed for accurate connection indicator
Date: 2025-03
Context: Browser showed "Pioneer: Connected" even when hardware was unplugged.
Problem: The WebSocket connection (browser↔Python server) was conflated with Pioneer hardware connectivity. The badge reflected whether the WS was open, not whether packets were arriving from hardware.
Fix: Added `pioneer_status` message type with `is_receiving` bool derived from last-packet timestamp + 5s stale timeout. A watchdog loop pushes this every 2s so the UI updates when Pioneer goes silent.
Prevention: Always distinguish transport connectivity (WS open) from data connectivity (packets arriving) in status indicators.

---

## Cross-Cutting / Workflow

### fix_route() wrapping must be applied at every call site, not just the manager
Date: 2026-03-18
Context: QA of BUG-BRIDGE-CYCLE fix. Testing `POST /api/network/route/fix` with a
nonexistent interface ("en16").
Problem: The "route: bad address" friendly error wrapping was added to `BridgeManager.fix_route()`
but `scue/api/network.py:fix_route_endpoint()` calls `network.route.fix_route()` directly,
bypassing the manager's method entirely. The raw kernel error still reaches the user.
Fix/Pattern: When adding error wrapping to a service-layer method, audit every API endpoint
that calls the same underlying function directly. Either (a) route all API calls through the
service layer, or (b) apply the wrapping at the lowest common point (the network module itself).
Prevention: If an error-wrapping fix lives in a class method, grep for direct calls to the
underlying function in API handlers. Do not assume the class method is the only call path.

### mock_bridge.py cannot simulate "hardware absent" when JAR + JRE are present
Date: 2026-03-18
Context: QA of BUG-BRIDGE-CYCLE. Attempted to use mock_bridge.py for SC-005/SC-011/SC-012.
Problem: `BridgeManager` checks JAR + JRE presence on every `start()`. When both are
available, the manager always attempts a real Java launch — mock_bridge.py (a WebSocket
server on port 17400) would conflict with the real bridge, not substitute for it. Testing
"no hardware" scenarios requires either physical disconnection or a config flag to bypass
JAR/JRE detection.
Fix/Pattern: Add an env var or config flag (e.g., `SCUE_FORCE_MOCK_BRIDGE=1`) that sets
`jar_exists=False` in the manager's checks, forcing it to skip the real Java launch path.
This unlocks SC-005/SC-010/SC-011/SC-012 in CI/mock environments.
Prevention: When designing mock infrastructure, consider that the real system may have all
prerequisites installed. Mock tooling needs a way to override real-system detection, not just
replace the binary.

### _last_message_time not reset in start() causes crash cycle on every restart
Date: 2026-03-18
Context: Live hardware QA of BUG-BRIDGE-CYCLE fix. Testing SC-001 (adapter unplug), SC-003 (board power off), SC-010 (user restart, board off).
Problem: `BridgeManager.start()` does not reset `_last_message_time` to `0.0` before launching a new subprocess. At initial server start, `_last_message_time=0.0` (class default), so the health check guard `if self._last_message_time > 0` is False — the silence check never fires — bridge stays stable. After any crash, `_last_message_time` holds the timestamp of the last message from the previous run. Health check fires within 10s of restart (old timestamp is >20s stale), before beat-link can reconnect — drives another crash — repeat. This creates a permanent crash cycle on every restart, defeating the BUG-BRIDGE-CYCLE fix for all hardware-disconnect scenarios.
Fix/Pattern: Add `self._last_message_time = 0.0` at the start of `start()`, before `_launch_subprocess()`. This gives beat-link the same clean 20s silence window on restarts that it gets on initial startup.
Prevention: Any health check that guards on `field > 0` depends on the field being initialized to 0 on fresh start. If the field is not reset on restart, the guard does not apply and the check fires immediately. Always reset health check timestamps in `start()` / reset methods.

### Renaming private attributes can break out-of-scope tests
Date: 2026-03-17
Context: Bridge L0 sessions — renaming internal attributes during refactoring.
Problem: Tests in other files outside the agent's scope may reference private attributes by name (e.g., `_restart_count`, `_last_message_time`). Renaming these attributes breaks those tests, but the agent doesn't know about them because they're outside scope.
Fix/Pattern: When renaming internal attributes, add backward-compatible property aliases on the class so old names still work. Flag the rename in the session summary under "Interface Impact" so the Operator can dispatch cleanup to the appropriate agent.
Prevention: Before renaming any private attribute, grep the test directory for references. If references exist outside your scope, use an alias rather than a breaking rename.

---

## Resolved

*(Items that are fixed at the code level but kept for historical context)*

### beat-link-trigger OSC approach abandoned
Context: Initially attempted to use beat-link-trigger OSC expressions to bridge Pioneer data.
Problem: Required the DJ to configure OSC expressions manually in beat-link-trigger; no turnkey setup. Expressions never configured, so no data arrived.
Resolution: Replaced entirely with beat-link library as managed subprocess (ADR-005 in new architecture). No beat-link-trigger dependency.

### Bridge listen loop crash does not auto-recover (fixed)
Date: 2026-03-17
Context: Investigating device discovery blocker — bridge reported is_receiving=true but devices stayed empty.
Problem: When _listen_loop errors (WebSocket disconnect), the handler set status="crashed" but did not call _schedule_restart(). The health check loop saw non-"running" status and exited its loop. Result: permanent "crashed" state with no recovery path. The Java subprocess could still be running with a dead WebSocket server (zombie process).
Fix: Added _schedule_restart() call in listen loop error handler. Also separated _last_pioneer_message_time from _last_message_time so is_receiving reflects actual Pioneer traffic, not bridge heartbeats.
Prevention: Any status transition to "crashed" should trigger restart logic. Audit all paths that set _status = "crashed" to ensure they either call _schedule_restart() or have a clear reason not to (e.g., no_jre/no_jar). Also: always check for zombie Java processes after unexpected bridge crashes — `ps aux | grep beat-link`.
### is_receiving can be inflated by bridge heartbeats (fixed)
Date: 2026-03-17
Context: Same investigation as above.
Problem: _last_message_time was updated by ALL WebSocket messages including bridge_status heartbeats. When VirtualCdj.start() failed, bridge_status error messages kept is_receiving flickering to true. Frontend showed "Pioneer traffic detected" when no Pioneer hardware was actually communicating.
Fix: Added separate _last_pioneer_message_time that only updates on device/player/beat messages. pioneer_status.is_receiving now derives from this. Added bridge_connected field for bridge process liveness.
Prevention: When building status indicators, always distinguish between "transport is alive" and "data source is producing data." They are different failure modes.

### Bridge crash-restart cycle when hardware absent (fixed)
Date: 2026-03-18
Context: Bridge entered unrecoverable crash-restart cycle when Pioneer USB-Ethernet adapter was unplugged or board powered off. Each restart stole macOS window focus ("beat link trigger" in menu bar).
Problem: Four compounding issues:
1. Health check checked `_last_message_time` silence as restart trigger. Bridge heartbeats keep this fresh while the process is up, so this was correct — but the intent was muddled. Pioneer hardware silence (`_last_pioneer_message_time`) is explicitly NOT a restart trigger; that was never the correct trigger.
2. `_consecutive_failures` reset to 0 on ANY `"running"` transition, including quick start-crash cycles (< 30 s). Each brief connection reset the counter, blocking fallback/waiting threshold from ever triggering.
3. After crash threshold, bridge entered "fallback" (UDP parser) which has no auto-recovery path to full bridge mode. Fallback also fails when interface doesn't exist (adapter unplugged).
4. Java subprocess launched without AWT-suppression JVM flags, so every launch stole macOS focus and identified as "beat link trigger".
Fix/Pattern:
1. Health check comment clarified: only bridge WebSocket heartbeat silence (all messages including bridge_status) triggers restart — NOT Pioneer traffic silence.
2. Added `_last_stable_start_time` + `_MIN_STABLE_UPTIME_S = 30 s`: `_consecutive_failures` only resets if the previous run lasted ≥ 30 s.
3. Replaced fallback transition with `waiting_for_hardware` state: slow-poll every 30 s with `start()`. Failure counter reset on entry so next cycle starts fresh. Fallback now reserved for JRE/JAR absent only.
4. Added `_JVM_FLAGS = ["-Djava.awt.headless=true", "-Dapple.awt.UIElement=true", "-Xdock:name=SCUE Bridge"]` inserted between "java" and "-jar" in the subprocess launch command.
5. Bonus: `fix_route()` in manager.py now wraps "route: bad address" kernel errors with a user-readable message.
Prevention:
- Any circuit-breaker pattern (failure count → fallback) must guard against "partial success" resetting the counter. If the code can briefly succeed before crashing, add a minimum stable uptime check.
- Always provide a recovery path from any fallback/degraded state. A terminal state with no recovery requires manual intervention.
- Health check silence conditions must be clearly scoped: are we checking bridge liveness or hardware data presence? They are different failure modes.
