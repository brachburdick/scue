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

### librosa beat tracking drifts on tempo-variable tracks
Date: 2025-03
Context: Analyzing progressive house tracks with gradual BPM shift.
Problem: librosa.beat.beat_track assumes constant tempo. Beats can drift by ~200ms over 5 minutes.
Fix: Use librosa beat tracking as the working reference only. After Pioneer enrichment pass, replace the librosa beatgrid with Pioneer's hand-verified rekordbox grid.
Prevention: Never rely solely on librosa beat grid for production timing. Always plan for Pioneer enrichment.

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
