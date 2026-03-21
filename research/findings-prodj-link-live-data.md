# Research Findings: Pro DJ Link Live Network Data — Waveform Lookahead & Status Latency

## Questions Addressed
1. When receiving real-time waveform data from XDJ/CDJ hardware over Pro DJ Link, how much "look ahead" beyond the current playback position is available?
2. Are button presses (play, cue, hot cues) sent as discrete low-latency events over ethernet, or via another mechanism?

---

## Findings

### Question 1: Waveform Lookahead — Full Track Available

**Answer:** The lookahead is the **entire track**, not a scrolling window. When a track is loaded on a player, any device on the network can request and receive the complete waveform data as a single blob via TCP from the player's dbserver. There is no partial/streaming model — you get everything from beat 1 to the last beat, all at once.

**Detail:**

#### Two waveform resolutions available via dbserver

| Type | dbserver message | Resolution | Data (5-min track) | Description |
|------|-----------------|------------|---------------------|-------------|
| **Waveform Preview** | `2004` (legacy) / `2c04` (NXS2+) | ~400 columns (entire track) | ~800 bytes | Birds-eye overview bar — entire track compressed into 400 two-byte pairs (height 0-31 + whiteness) |
| **Waveform Detail** | `2904` | ~150 half-frames/sec (entire track) | ~90-135 KB | High-resolution scrolling waveform. A 5-min track = ~45,000 columns |

#### How it works

1. Track loads on CDJ/XDJ
2. Another device on the LAN sends a TCP request to the player's dbserver with the track's rekordbox ID
3. Player responds with the **complete waveform data** for the entire track
4. The requesting device renders the playhead position client-side on top of this complete dataset

There is no "streaming" of waveform data during playback. The entire blob is fetched once. This is the same mechanism beat-link's `WaveformFinder` uses (though on DLP hardware, the MetadataFinder dependency breaks this path — see `findings-waveform-trackid.md` Q3).

#### What this means for SCUE

With the full track waveform available from the moment of load, SCUE can:
- See the **entire remaining track** from current playhead to end
- Analyze upcoming energy levels, breakdowns, drops, quiet sections **arbitrarily far in advance**
- The constraint is not data availability — it's the quality of the analysis SCUE performs on that data

#### SCUE's access path (DLP hardware)

On DLP devices (XDJ-AZ, Opus Quad, CDJ-3000X), beat-link's WaveformFinder is broken (MetadataFinder dependency). SCUE accesses equivalent data via:
- **USB ANLZ files** parsed by pyrekordbox during USB scan (see `findings-anlz-waveform-formats.md`)
- PWV5 (color detail, .EXT) and PWV7 (3-band detail, .2EX) provide the same ~150 entries/sec full-track data
- This data is available **before playback even begins** — from the moment the USB is scanned

**Sources:**
- Deep Symmetry djl-analysis — Track Metadata: https://djl-analysis.deepsymmetry.org/djl-analysis/track_metadata.html (HIGH)
- beat-link WaveformDetail API (`getFrameCount()`, `getTotalTime()` confirm full-track scope): https://deepsymmetry.org/beatlink/apidocs/org/deepsymmetry/beatlink/data/WaveformDetail.html (HIGH)
- beat-link WaveformPreview API: https://deepsymmetry.org/beatlink/apidocs/org/deepsymmetry/beatlink/data/WaveformPreview.html (HIGH)
- DJ Link Ecosystem Analysis — dbserver message types: https://djl-analysis.deepsymmetry.org/djl-analysis/packets.html (HIGH)

**Confidence:** HIGH. Confirmed by beat-link API (exposes full-track frame count and duration), dbserver protocol documentation, and consistency with SCUE's existing ANLZ findings.

---

### Question 2: Button Press / Status Update Latency

**Answer:** Button presses are **not sent as discrete low-latency events**. They appear as state changes in periodic UDP status packets broadcast every ~200ms (~5 Hz). Worst-case detection latency for a button press is ~200ms, average ~100ms. Beat timing packets are a separate, beat-synchronous channel.

**Detail:**

#### Status packets (port 50002) — ~200ms polling cycle

Each CDJ/XDJ broadcasts UDP status packets approximately every 200 milliseconds. These contain the cumulative player state, not individual events:

| Field | Packet bytes | What it captures |
|-------|-------------|-----------------|
| Play state | `0x89` bit 6 | Playing vs idle (play/pause button) |
| Play mode | `0x7B`, `0x8B` | Additional play mode indicators |
| Sync/Master/On-Air | `0x89` other bits | Sync, master, on-air flags |
| Cue countdown | `0xA4-0xA5` | Bars remaining to next saved cue point |
| Beat counter | `0xA0-0xA3` | Absolute beat position in track |
| Beat within bar | `0xA6` | 1-4 position within current bar |
| Hot cue change | `0x5A-0x5B` | Set to `0xFFFF` when a hot cue is added/deleted |

**Latency profile:**
- A button press (play, cue, hot cue, sync) changes internal state on the player
- That state change appears in the **next** status packet
- At ~5 Hz broadcast rate: **worst case ~200ms, average ~100ms**
- During jog wheel manipulation, some newer players increase status packet frequency

#### Beat packets (port 50001) — beat-synchronous, lowest latency timing

Beat packets are sent **once per beat** at the current tempo:

| Tempo | Beat packet interval |
|-------|---------------------|
| 120 BPM | ~500ms |
| 140 BPM | ~429ms |
| 174 BPM | ~345ms |

Each beat packet includes:
- `nextBeat` (bytes `0x24-0x27`): milliseconds until the next beat
- `2ndBeat` (bytes `0x28-0x2B`): milliseconds until the beat after that
- `nextBar` (bytes `0x2C-0x2F`): milliseconds until the next bar boundary

These are the **lowest-latency timing signals** in the protocol — they arrive precisely on the beat.

#### Packet sizes by hardware generation

| Hardware | Status packet size |
|----------|-------------------|
| CDJ-2000NXS (original Nexus) | `0xD4` bytes |
| CDJ-2000NXS2 | `0x11C` bytes |
| CDJ-3000 | `0x200` bytes |

#### What this means for SCUE

- **For lighting/visual triggers on the beat:** Beat packets on port 50001 provide beat-accurate timing. This is the right signal for beat-reactive effects.
- **For detecting DJ actions (play/pause, hot cue jumps, track load):** ~100-200ms detection latency via status packets. Acceptable for visual response but not for sub-frame accuracy.
- **Not an event bus:** The protocol is polling-based, not event-driven. There is no "button pressed" message. SCUE must diff consecutive status packets to detect state transitions.

**Sources:**
- DJ Link Ecosystem Analysis — Packet Types: https://djl-analysis.deepsymmetry.org/djl-analysis/packets.html (HIGH)
- DJ Link Ecosystem Analysis — Detailed Device Status: https://djl-analysis.deepsymmetry.org/djl-analysis/vcdj.html (HIGH)
- Deep Symmetry beat-link source: https://github.com/Deep-Symmetry/beat-link (HIGH)
- Deep Symmetry dysentery (protocol analysis): https://github.com/Deep-Symmetry/dysentery (HIGH)

**Confidence:** HIGH. The ~200ms status packet interval and beat packet timing are well-documented in the DJ Link ecosystem analysis and confirmed by multiple independent implementations (beat-link, prolink-go, prolink-connect).

---

## Implications for SCUE Architecture

### Full-track lookahead enables predictive cue generation

Since SCUE has the entire waveform + analysis data from the moment a track loads (via ANLZ parsing), Layer 2 cue generation does not need to be purely reactive. It can:

1. **Pre-compute the entire cue timeline** for the loaded track at load time
2. **Look ahead** to upcoming sections (drops, breakdowns, builds) and prepare effects in advance
3. **Schedule transitions** — e.g., start a slow color fade 16 bars before a drop, knowing exactly when it arrives
4. **Adapt in real-time** only when the DJ deviates from linear playback (loops, hot cue jumps, scratching)

### Status packet latency is acceptable for visual sync

~100-200ms is within the threshold for visually-coupled lighting response. Human perception of audio-visual sync tolerates ~50-80ms of offset. Combined with beat packet timing (which is beat-precise), SCUE can:

1. Use **beat packets** for rhythmic effects (strobe, pulse, chase) — these are the timing backbone
2. Use **status packet diffs** for detecting DJ intent (track change, loop engage, hot cue jump) — the ~100ms average latency is invisible to the audience
3. The beat packets provide the low-latency clock; status packets provide the semantic context

### Recommended data flow

```
Track loads on deck
  → Bridge emits player_status with rekordbox_id
  → Layer 1 resolves track identity (composite key → USB metadata)
  → Layer 1 loads full ANLZ waveform data (already parsed during USB scan)
  → Layer 2 pre-computes ENTIRE cue timeline for the track
  → Layer 3 receives cue timeline + begins scheduling effects
  → Beat packets drive real-time effect execution
  → Status packet diffs trigger re-planning when DJ deviates from linear playback
```

---

## Recommended Next Steps

1. **Quantify "deviation detection" latency.** When the DJ hits a hot cue or engages a loop, how quickly can SCUE detect it and re-plan? Measure: bridge → Python adapter → Layer 1 status diff → Layer 2 re-plan. The ~100ms network latency is one component; the full pipeline latency determines whether pre-planned cues can be interrupted smoothly.

2. **Design the predictive cue timeline data structure.** Layer 2 needs a structure that represents the full planned cue sequence for a track but supports efficient invalidation/re-planning when playback deviates. This is a key architectural decision.

3. **Prototype beat packet → effect trigger path.** Measure end-to-end latency from beat packet arrival at the bridge through to DMX/OSC output. This validates whether the beat-synchronous path meets the <20ms target for perceptually tight lighting sync.
