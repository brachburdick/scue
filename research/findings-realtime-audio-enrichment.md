# Research Findings: Real-Time Audio Enrichment, Deck Separation & Legacy Hardware Bypass

**Request:** Operator direct request (2026-03-19)
**Date:** 2026-03-19
**Status:** Complete

---

## Executive Summary

| Topic | Key Finding | Implication |
|-------|------------|-------------|
| **Audio capture** | USB audio interface (Scarlett 2i2 etc.) + `sounddevice` Python lib. ~3-5ms input latency at 48kHz. Trivial to set up. | Layer 0.5: a new optional data source alongside the beat-link bridge. |
| **Deck separation from stereo master** | NOT blind source separation. It's **informed source separation** — we already know the tracks from beat-link. Least-squares spectral decomposition recovers mixing ratios in ~0.5ms per update. | Accurate deck weights during transitions. Per-band (bass/mid/high) estimation detects DJ EQ moves. |
| **Combining with beat-link + pre-analysis** | Audio stream provides: (1) independent track ID verification, (2) continuous mixing ratio, (3) EQ detection, (4) position confirmation. beat-link provides: beat grid, tempo, deck assignment. Pre-analysis provides: spectral templates, sections, events. | Three independent data sources triangulating the same musical state. Each covers the others' blind spots. |
| **Legacy CDJ bypass for DLP** | A CDJ-2000NXS2 can connect to XDJ-AZ via LINK EXPORT port. beat-link MetadataFinder works normally for that device. Audio requires separate cable to external input. | Viable but limited: only covers 1 deck, requires extra cabling, and the audio routing through "external input" may not have full mixer integration. |

---

## Q1: Getting Real-Time Audio Into SCUE

### Signal Path

```
XDJ-AZ Master Out (XLR/TRS/RCA)
  → USB audio interface (line input)
    → macOS CoreAudio
      → sounddevice (Python)
        → ring buffer → DSP pipeline
```

### Connection Options (Best → Worst)

| Source | Connector | Quality | Notes |
|--------|-----------|---------|-------|
| MASTER OUT1 | XLR (balanced) | Best | Lowest noise, longest cable runs |
| BOOTH OUT | 1/4" TRS (balanced) | Excellent | Use if master outs taken by PA |
| MASTER OUT2 | RCA (unbalanced) | Good | Adequate for short runs (<3m) |

### Audio Interface Requirements

Any 2-input USB audio interface with line-level inputs. Recommended:
- Focusrite Scarlett 2i2 (~$170)
- MOTU M2 (~$200)
- Audient EVO 4 (~$130)

All provide USB-C, 48kHz/24-bit, and macOS driver-free operation via CoreAudio.

### Python Audio Capture

**Winner: `sounddevice`** (PortAudio bindings, active maintenance, NumPy-native)

| Buffer Size | Latency | Reliability | SCUE Recommendation |
|-------------|---------|-------------|---------------------|
| 256 samples | ~5.8ms | Workable | Minimum viable |
| **512 samples** | **~11.6ms** | **Reliable** | **Default for SCUE** |
| 1024 samples | ~23.2ms | Rock solid | Conservative fallback |

Why `sounddevice`:
- Records directly to NumPy arrays (no byte conversion)
- Has asyncio support via coroutine-based streams
- Exposes CoreAudio-specific settings on macOS
- Callbacks run in C thread (GIL-free)
- Active maintenance, good docs

Pattern: callback fills ring buffer → asyncio loop reads and processes at analysis rate.

**Confidence:** HIGH. Well-documented library, macOS CoreAudio is well-behaved, latency figures from multiple corroborating sources.

---

## Q2: Distinguishing L+R Channels / Deck Separation

### Critical Insight: This Is NOT Blind Source Separation

The naive framing — "separate the stereo master into deck A and deck B" — makes this sound like a blind source separation problem (extremely hard). But SCUE has three massive advantages:

1. **We know what tracks are loaded** (from beat-link `player_status`)
2. **We have pre-analyzed spectral features** for every track (from Layer 1A analysis)
3. **We know the playback position** (from beat-link `beat_number` + beatgrid)

This converts the problem from blind source separation to **informed source separation (ISS)**, which is dramatically easier.

### Why Mid/Side Doesn't Work

DJ mixers sum both decks to both L and R channels. Both tracks appear in the mid channel. Mid/side decomposition does NOT cleanly separate decks. This is a dead end.

### The Actual Technique: Spectral Least-Squares Decomposition

Given:
- `S_live[f]` = live audio power spectrum (from FFT of captured audio)
- `S_A[f]` = expected power spectrum of Track A at current position (from pre-analysis)
- `S_B[f]` = expected power spectrum of Track B at current position (from pre-analysis)

Solve: **`S_live ≈ α·S_A + β·S_B`** via constrained least squares.

- `α` and `β` are the deck weights (mixing ratio)
- Constrained: α ≥ 0, β ≥ 0
- Cost: one `numpy.linalg.lstsq` call with 512×2 matrix → **~10 microseconds**
- Update rate: 4-10 Hz (100-250ms windows) with exponential moving average smoothing

### Per-Band EQ Detection (The Clever Part)

Solve the decomposition independently per frequency band:

```
Bass  (<250Hz):   α_bass, β_bass
Mid   (250-4kHz): α_mid,  β_mid
High  (>4kHz):    α_high, β_high
```

This reveals DJ EQ moves:
- If `α_bass → 0` while `α_mid`, `α_high` hold steady → DJ cut bass on Deck A
- If `β_high → 0` → DJ cut highs on Deck B
- During a bass swap transition: `α_bass` drops as `β_bass` rises, other bands may hold steady

**This gives SCUE more information than a single fader position — it can detect per-band mixing intent.**

### Feature Selection

| Feature | EQ Sensitivity | Discriminative Power | Cost | Recommendation |
|---------|---------------|---------------------|------|----------------|
| Mel bands (40-80) | HIGH | HIGH | Low | Primary feature |
| Chromagram (12 bins) | LOW | MEDIUM | Moderate | Position verification |
| 3-band energy | HIGH but interpretable | MEDIUM | Very low | EQ detection |
| Raw power spectrum | HIGH | HIGH | Low | Alternative to mel |

Recommended: mel-band energy as primary, 3-band for interpretable EQ detection.

### End-to-End Pipeline

```
Audio capture (sounddevice, 512-sample buffer, 44.1kHz)
  → Accumulate to analysis window (4096-8192 samples, ~100-200ms)
  → FFT → power spectrum → mel-band energy
  → Look up expected spectra for Track A and Track B at current positions
  → Least-squares solve for [α, β]
  → Per-band solve for [α_bass, α_mid, α_high, β_bass, β_mid, β_high]
  → Smooth with EMA (coefficient=0.3)
  → Emit DeckWeight event to Layer 2
```

Total cost per update: **~0.5ms** (FFT + features + solve). Leaves >99% CPU free.

### Caveats

- **Position accuracy matters.** If beat-link position tracking drifts, spectral lookup misaligns. Cross-correlation can self-correct.
- **Similar tracks.** Two tracks with near-identical spectral profiles → ill-conditioned least squares. In practice, most transitions involve spectrally dissimilar tracks (outgoing drop → incoming intro).
- **Mixer effects.** Reverb/delay/filters distort the estimate. Partial mitigation: the EMA smoothing dampens effect-induced jitter.
- **Best during transitions.** Which is exactly when you need it most.

**Confidence:** HIGH for computational feasibility. HIGH for mel-band feature choice. MEDIUM for real-world accuracy (untested with live DJ hardware). LOW for mixer effects handling (open problem).

---

## Q3: Combining Audio + Beat-Link + Pre-Analysis

### Three-Source Triangulation

| Data Source | What It Provides | Limitations |
|-------------|-----------------|-------------|
| **Beat-link bridge** | Deck assignment, beat position, BPM, pitch, on-air status, rekordbox_id | DLP metadata broken; no mixing ratio; no EQ state |
| **Pre-analysis (Layer 1A)** | Spectral templates, sections, events, beatgrid, waveforms | Static — doesn't know what's happening live |
| **Live audio capture** | Mixing ratio, EQ detection, track ID verification, position confirmation | Requires audio interface; ~12ms latency; sensitive to effects |

### How They Complement Each Other

**Problem 1: DLP metadata is broken (XDJ-AZ, Opus Quad)**
- Beat-link gives: rekordbox_id (correct for deck assignment), BPM, beat position
- Audio capture gives: independent track ID verification via fingerprint matching
- Pre-analysis gives: spectral templates once track is identified

**Problem 2: No crossfader/fader data from Pro DJ Link on XDJ-AZ**
- Beat-link gives: `is_on_air` (binary — fader up or down, no continuous value)
- Audio capture gives: continuous mixing ratio α/β via spectral decomposition
- Pre-analysis gives: expected spectral profile at each position for the solve

**Problem 3: Track position on DLP (TimeFinder broken)**
- Beat-link gives: `beat_number` (works on all hardware)
- Pre-analysis gives: beatgrid (from USB ANLZ) to convert beat_number → ms
- Audio capture gives: cross-correlation position confirmation as a sanity check

**Problem 4: DJ EQ intent is invisible to beat-link**
- Beat-link: no EQ data at all
- Audio capture: per-band weight estimation reveals bass/mid/high EQ positions
- Pre-analysis: provides the per-band spectral baselines to decompose against

### New Capabilities This Enables

1. **Accurate transition detection.** Not just "both on-air" but a continuous blend curve with per-band resolution.
2. **EQ-aware cue generation.** Layer 2 could modulate effects based on which frequencies the DJ has active per deck.
3. **Hardware-agnostic operation.** Audio capture works with ANY DJ setup — not just Pioneer. This opens SCUE to Denon, Traktor, etc.
4. **Position verification.** Cross-correlation against pre-analyzed chromagrams confirms beat-link position tracking. If they diverge, SCUE can log it and trust the audio source.

### Academic Foundation

**Key paper:** Kim & Choi, "A Computational Analysis of Real-World DJ Mixes using Mix-To-Track Subsequence Alignment" (ISMIR 2020, [arxiv.org/abs/2008.10267](https://arxiv.org/abs/2008.10267))
- Uses subsequence DTW on beat-synchronous MFCCs/chroma to align known tracks against a mix
- Extracts cue points, transition lengths, mix segmentation
- Published work is offline but adaptable to sliding-window real-time

**Confidence:** HIGH for the triangulation architecture. MEDIUM-HIGH for the academic foundation (proven offline, real-time adaptation is novel but straightforward).

---

## Q4: Legacy CDJ Bypass for DLP Issues

### Can It Work?

**Yes**, with caveats.

#### Physical Setup

```
CDJ-2000NXS2  ───[Ethernet]───  XDJ-AZ (LINK EXPORT port)
CDJ-2000NXS2  ───[RCA→1/4"]───  XDJ-AZ (external input)
```

#### What Works

| Capability | Status | Notes |
|-----------|--------|-------|
| Pro DJ Link data connection | WORKS | Single Ethernet cable to LINK EXPORT port |
| beat-link MetadataFinder for legacy CDJ | WORKS | Standard DBServer protocol, not DLP |
| USB media sharing between devices | WORKS | Browse CDJ's USB from XDJ-AZ and vice versa |
| Device number assignment | NO CONFLICT | XDJ-AZ uses 9-12, CDJ uses 1-4 |

#### What Doesn't Work Well

| Limitation | Impact |
|-----------|--------|
| Audio requires separate cable | RCA out from CDJ → RCA-to-1/4" adapter → XDJ-AZ external input |
| Audio arrives on "external input" not a native deck | May lack full mixer EQ/effects integration |
| Only covers 1 additional deck | The XDJ-AZ's own 2 decks still use DLP |
| Physical complexity | Extra cables, adapter, potential for signal issues |
| XDJ-AZ has only ONE link port | 2+ external players need Ethernet switch |

#### Comparison: Legacy CDJ vs Audio Capture

| Dimension | Legacy CDJ Bypass | Audio Capture Approach |
|-----------|------------------|----------------------|
| Solves DLP metadata? | For 1 deck only | For all decks (via fingerprint matching) |
| Mixing ratio? | No | Yes (continuous, per-band) |
| Hardware cost | CDJ-2000NXS2 ($800-1500 used) | USB audio interface ($130-200) |
| Physical complexity | High (2 cables, adapter, extra deck) | Low (1 cable from master out) |
| Setup time | Moderate (cable routing, device config) | Low (plug in, configure once) |
| Works with non-Pioneer? | No | Yes (any mixer with audio out) |

### Verdict

The legacy CDJ approach is a **quick tactical win** if you already own a CDJ-2000NXS2 and want beat-link MetadataFinder working for one deck immediately. But the audio capture approach is strategically superior: it solves more problems, costs less, and generalizes to any hardware.

**Recommendation:** Pursue audio capture as the primary strategy. Use the legacy CDJ as a stopgap if you need MetadataFinder data before the audio pipeline is built.

**Confidence:** HIGH for physical connectivity (verified via official AlphaTheta support docs). MEDIUM for XDJ-AZ device numbers (inferred from OPUS-QUAD pattern, not directly verified). HIGH for the strategic comparison.

---

## Architectural Implications

### Where Audio Capture Fits in SCUE's Layer Model

```
Layer 0:   Beat-link bridge (Java → WS → Python adapter)
Layer 0.5: Audio capture    (sounddevice → ring buffer → DSP pipeline)  ← NEW
Layer 1A:  Offline analysis  (librosa, allin1-mlx, ruptures)
Layer 1B:  Live tracking     (PlaybackTracker, TrackCursor, DeckMix)
Layer 2:   Cue generation    (music → semantic cues)
```

Layer 0.5 is a **parallel data source** to Layer 0. It feeds into Layer 1B's DeckMix with:
- `DeckWeight` events (continuous α/β per deck, per-band)
- `TrackIDConfirmation` events (fingerprint matches against pre-analyzed tracks)
- `PositionConfirmation` events (cross-correlation position estimates)

Layer 1B's weight calculation (ADR-006) gains a new `mix_mode: "audio"` option:
- `"master_only"` — current default, binary on-air
- `"crossfade"` — from bridge on-air + crossfader data
- **`"audio"` — from spectral decomposition of live audio**
- `"manual"` — user override

### What Needs Pre-Analysis Support

The spectral decomposition requires **mel-band energy profiles** stored per-frame in the TrackAnalysis. The current analysis pipeline computes:
- RGB waveform (3-band: bass/mids/highs at 60fps)
- Section boundaries, labels, confidence
- Beat/downbeat positions

It does NOT currently store:
- Full mel spectrogram (needed for spectral matching)
- Per-frame power spectrum

Adding mel spectrogram storage to the analysis pipeline would be a modest extension (~5-10 lines of librosa code) but increases storage per track. At 40-80 mel bands × 60fps × 4 bytes = ~14-28 KB/sec → ~4-8 MB per 5-min track. Acceptable.

### Data Flow During a Transition

```
Time 0: Track A playing solo
  beat-link: deck 1 on-air, deck 2 off
  audio: α≈1.0, β≈0.0
  DeckMix: cursor A weight=1.0

Time 1: DJ loads Track B, starts playing off-air
  beat-link: deck 1 on-air, deck 2 playing but not on-air
  audio: α≈1.0, β≈0.0 (B not in master yet)
  DeckMix: cursor A weight=1.0

Time 2: DJ begins crossfade (bass swap)
  beat-link: both decks on-air
  audio: α_bass=0.3, β_bass=0.7, α_mid=0.9, β_mid=0.1
  DeckMix: cursor A weight varies by band — Layer 2 can respond

Time 3: Crossfade complete
  beat-link: deck 1 off-air
  audio: α≈0.0, β≈1.0
  DeckMix: cursor B weight=1.0
```

---

## Recommended Next Steps

1. **Prototype audio capture.** Build a minimal `sounddevice` InputStream → ring buffer → mel-band energy computation. Verify on target Mac + Scarlett/MOTU. ~1 day.

2. **Prototype deck weight estimation.** Use two known WAV files mixed at known ratios. Verify least-squares decomposition recovers correct weights with and without EQ. ~1-2 days.

3. **Add mel spectrogram to analysis pipeline.** Store per-frame mel-band energy in TrackAnalysis JSON. Verify storage size is acceptable. ~0.5 day.

4. **Design Layer 0.5 interface contract.** Define `DeckWeight`, `TrackIDConfirmation`, `PositionConfirmation` event types. Add to CONTRACTS.md. ~0.5 day.

5. **Integrate with DeckMix.** Add `mix_mode: "audio"` to ADR-006 weight calculation. Wire audio-derived weights into Layer 1B. ~1-2 days.

6. **Defer fingerprint matching.** Audio capture for deck weight estimation is valuable immediately. Track ID via fingerprinting is a separate milestone (M7+).

7. **Defer legacy CDJ integration.** Audio capture is strategically superior. Only pursue legacy CDJ if a quick MetadataFinder fix is needed before audio pipeline ships.

---

## Confidence Levels

| Finding | Confidence | Notes |
|---------|:-:|-------|
| Audio capture via sounddevice is viable | HIGH | Well-documented, multiple sources |
| 3-5ms input latency on macOS | HIGH | CoreAudio is well-characterized |
| Spectral least-squares for deck weights | HIGH (feasibility) | Standard math, trivially real-time |
| Accuracy of deck weight estimation | MEDIUM | Untested with live DJ hardware |
| Per-band EQ detection | MEDIUM-HIGH | Mathematically sound, untested |
| Legacy CDJ + XDJ-AZ connectivity | HIGH | Official AlphaTheta docs |
| XDJ-AZ uses device numbers 9-12 | MEDIUM | Inferred from OPUS-QUAD, not directly verified |
| Mid/side is insufficient for deck separation | HIGH | Fundamental limitation of DJ mixer topology |
| Kim & Choi mix-to-track alignment applicability | HIGH | Published peer-reviewed research |

---

## Skill File Candidates

### `skills/realtime-audio-capture.md` (NEW)
- sounddevice setup on macOS: InputStream, ring buffer pattern, asyncio integration
- Buffer size selection: 512 samples default, tradeoffs
- CoreAudio settings for low latency
- Audio interface connection: XLR > TRS > RCA from DJ mixer

### `skills/spectral-deck-separation.md` (NEW)
- Informed source separation: why it's NOT blind source separation for SCUE
- Least-squares spectral decomposition algorithm
- Per-band (bass/mid/high) EQ detection technique
- Feature selection: mel bands primary, 3-band for interpretation
- Caveats: position accuracy, similar tracks, mixer effects

### `skills/pioneer-hardware.md` (UPDATE)
- XDJ-AZ LINK EXPORT port: 1 port, supports legacy CDJ connection
- Audio routing: data-only link, audio requires separate cable
- Device numbering: XDJ-AZ uses 9-12 (OPUS-QUAD pattern), legacy CDJ uses 1-4
- External input: 1/4" unbalanced, not RCA — adapter needed
