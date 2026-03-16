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

## Resolved

*(Items that are fixed at the code level but kept for historical context)*

### beat-link-trigger OSC approach abandoned
Context: Initially attempted to use beat-link-trigger OSC expressions to bridge Pioneer data.
Problem: Required the DJ to configure OSC expressions manually in beat-link-trigger; no turnkey setup. Expressions never configured, so no data arrived.
Resolution: Replaced entirely with beat-link library as managed subprocess (ADR-005 in new architecture). No beat-link-trigger dependency.
