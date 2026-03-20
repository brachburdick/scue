# Research Findings: Bridge Data Strategy — Waveforms, DLP IDs, Data Flow & Fingerprinting

**Request:** `research/research-request-bridge-data-strategy.md`
**Date:** 2026-03-19
**Status:** Complete (all 4 question groups answered)

---

## Executive Summary

| Topic | Key Finding | Action |
|-------|------------|--------|
| **Waveforms** | WaveformFinder works on legacy + XDJ-XZ but CANNOT be re-enabled for DLP hardware (hard dependency on MetadataFinder, same ID mismatch). pyrekordbox reads all waveform tags from USB ANLZ. | Use USB ANLZ waveform reading as universal path for all hardware. |
| **DLP IDs** | Volatile auto-increment keys — change on re-export, collide across USBs. Current `track_ids` table uses bare `rekordbox_id` (multi-USB bug). | Composite key `(source_player, source_slot, rekordbox_id)`. Tiered reconciliation: composite key → path stem → title+artist. |
| **Data flow** | Hybrid (analysis-first primary, deck-triggered fallback) matches existing infrastructure and beats every competitor. | Add `DeckAnalysisState` enum + "pending" path to TrackCursor. Beat-reactive defaults while analysis runs. |
| **Fingerprinting** | No suitable existing library. Custom implementation ~500-800 lines, 2-3 dev-days. | Add at M7 (Event Detection) when analysis pipeline is already being modified. Standard hashing first, tempo-invariant later. |

---

## Q1: WaveformFinder Hardware Compatibility

### Compatibility Matrix

| Hardware | MetadataFinder | WaveformFinder (dbserver) | USB ANLZ Waveform (pyrekordbox) |
|----------|:-:|:-:|:-:|
| CDJ-2000 (original) | WORKS | WORKS (blue only) | WORKS |
| CDJ-2000NXS | WORKS | WORKS (blue only) | WORKS |
| CDJ-2000NXS2 | WORKS | WORKS (blue + RGB) | WORKS |
| CDJ-3000 | WORKS | WORKS (blue + RGB + 3-band) | WORKS |
| XDJ-1000 / XDJ-1000MK2 | WORKS | WORKS | WORKS |
| XDJ-XZ | WORKS | WORKS | WORKS |
| Opus Quad | BROKEN (no dbserver) | BROKEN (no dbserver) | WORKS |
| XDJ-AZ | BROKEN (DLP ID mismatch) | BROKEN (DLP ID mismatch) | WORKS |
| OMNIS-DUO | BROKEN (DLP ID mismatch) | BROKEN (DLP ID mismatch) | WORKS |
| CDJ-3000X | BROKEN (DLP ID mismatch) | BROKEN (DLP ID mismatch) | WORKS |

### Key Findings

1. **XDJ-XZ is NOT classified as DLP by beat-link.** `DeviceAnnouncement.isUsingDeviceLibraryPlus` is only set for Opus Quad and XDJ-AZ. The XDJ-XZ uses standard Pro DJ Link dbserver and is treated like a CDJ-2000NXS2 pair + mixer.

2. **WaveformFinder CANNOT be selectively re-enabled for DLP hardware.** Three reasons:
   - `WaveformFinder.start()` explicitly calls `MetadataFinder.getInstance().start()` — hard dependency
   - WaveformFinder is event-driven from MetadataFinder's `TrackMetadataListener`
   - `getWaveformDetail()` sends the same rekordboxId to the dbserver that causes wrong metadata lookups — it returns the wrong track's waveform

3. **ADR-012's blanket disabling was architecturally correct**, not collateral damage.

4. **pyrekordbox reads all waveform ANLZ tags:** PWAV (blue preview), PWV3 (blue detail), PWV4 (color preview), PWV5 (color detail), PWV6/PWV7 (3-band). This is a complete USB-based replacement for all hardware types.

### Recommendation

Use USB ANLZ waveform reading via pyrekordbox as the **universal waveform source** for all hardware. This eliminates the need to maintain two code paths and is consistent with ADR-012/ADR-013.

**Full details:** `research/waveform-finder-hardware-compatibility.md`

---

## Q2: DLP Track ID Reliability & Reconciliation

### ID Stability Matrix

| Field | Stable Within USB | Stable Across USBs | Stable Across Re-exports |
|-------|:-:|:-:|:-:|
| DLP `content.id` (rekordbox_id) | YES | NO | NO |
| Legacy DeviceSQL rekordbox ID | YES | NO | NO |
| File path on USB | YES | USUALLY | NO |
| Title + Artist | YES | YES | YES |
| SHA256 of original audio | YES | YES | YES |

### Key Findings

1. **DLP IDs are volatile.** Auto-increment SQLite keys, assigned during export. Change on re-export. Independent per USB.

2. **Multi-USB collision is guaranteed.** Both USBs use auto-increment from 1. beat-link already reports `track_source_player` and `track_source_slot` in every `player_status` message.

3. **Current `track_ids` table has a multi-USB bug** — uses bare `rekordbox_id` as primary key. Needs composite key `(source_player, source_slot, rekordbox_id)`.

4. **Legacy DeviceSQL IDs have identical volatility** — same auto-increment pattern. The difference is legacy hardware supports MetadataFinder directly.

### Recommended Reconciliation Algorithm

**During USB scan:**
1. Composite key lookup `(source_player, source_slot, rekordbox_id)` — instant
2. File path stem match — instant (handles Pioneer filename truncation)
3. Normalized title+artist match — instant
4. Unmatched → log, wait for deck-triggered on-demand analysis

**During live deck load:**
1. Composite key lookup (pre-scanned) — instant
2. If USB mounted: rbox lookup → path stem → title+artist
3. Unmatched → fire `unknown_track` event, UI shows rbox metadata, no SCUE analysis

### Action Items
- Change `track_ids` to composite primary key
- Add stale-scan detection (compare rbox metadata against stored analysis on match)
- Consider re-enabling MetadataFinder for legacy-only hardware (ADR amendment)

**Full details:** `research/dlp-track-id-reliability.md`

---

## Q3: Deck-First vs Analysis-First Data Flow

### Recommendation: Hybrid (analysis-first primary, deck-triggered fallback)

**Rationale:**
1. Analysis-first infrastructure is already built (FE-4, USB scanner, batch analysis, fingerprint dedup)
2. On-demand fallback takes 3-8s — acceptable since DJs almost always load on the off-air deck with prep time
3. SoundSwitch (closest competitor) requires pre-analysis with no on-demand fallback. SCUE's hybrid is more capable.
4. Modest changes to PlaybackTracker — no changes to Layer 1→2 contract

### TrackCursor State Machine

```
            [Track loads on deck]
                     |
                     v
          ┌──────────────────┐
          │    RESOLVING     │  rekordbox_id → SQLite lookup
          └──────┬───────────┘
                 |
        ┌────────┴────────┐
        |                 |
  fp found           fp not found
        |                 |
        v                 v
 ┌──────────┐    ┌────────────────┐
 │ LOADING  │    │   UNMATCHED    │  Attempt audio file lookup
 └────┬─────┘    └───────┬────────┘
      |                  |
 analysis found    ┌─────┴──────┐
      |           yes           no
      v            |             |
 ┌──────────┐      v             v
 │  READY   │  ┌──────────┐  ┌──────────────┐
 └──────────┘  │ ANALYZING│  │ UNAVAILABLE  │
               │  (3-8s)  │  │              │
               └────┬─────┘  └──────────────┘
                    |           Beat-reactive
                    v           defaults only
               ┌──────────┐
               │  READY   │
               └──────────┘
```

### Layer 2 Behavior Per State

| State | Cue Engine Behavior |
|-------|-------------------|
| RESOLVING / LOADING | Hold previous state or idle |
| READY | Full section-aware cue generation |
| ANALYZING | Beat-reactive defaults: strobe on downbeat, color cycle per bar |
| UNAVAILABLE | Beat-reactive defaults indefinitely |

### Competitor Comparison

| Product | Pre-analysis | On-demand analysis | Section-aware |
|---------|:-:|:-:|:-:|
| SoundSwitch | Required | No | Yes (from rekordbox) |
| Lightkey | Recommended | Basic (energy only) | Partial |
| ShowKontrol | Manual authoring | No | N/A |
| **SCUE (proposed)** | **Recommended** | **Full (3-8s fallback)** | **Yes** |

### Implementation Scope
- `DeckAnalysisState` enum in `models.py`
- Refactor `PlaybackTracker._load_track_for_player()` to set state + trigger async analysis
- `get_deck_state()` method + WebSocket `analysis_status` event
- No changes to TrackCursor contract — Layer 2 handles `None` cursor with fallback

---

## Q4: Audio Fingerprinting Timeline

### Library Comparison

| Library | Last Maintained | Py 3.11+ | Algorithm | Tempo Handling | DB Backend | License | SCUE Fit |
|---------|:-:|:-:|---------|---------|---------|:-:|:-:|
| dejavu | 2020 | No (pinned ancient deps) | Constellation map | None | MySQL/PostgreSQL | MIT | Poor |
| audfprint | 2019 | Likely | Constellation map | None | pickle file | MIT | Moderate |
| chromaprint | 2026 | Yes | Chroma-based (NOT constellation) | Partial | AcoustID web service | LGPL-2.1 | Poor |
| **Custom** | N/A | Yes | Constellation map | Any | JSON/SQLite | N/A | **Best** |

### Key Findings

1. **Build custom.** ~500-800 lines using existing librosa/numpy/scipy. Zero new dependencies. 2-3 dev-days.

2. **Offline generation is cheap:** +0.5-1.5s per track, ~50-200KB storage. ~15-25% increase to current pipeline time.

3. **Tempo-invariant hashing (approach #3) has no existing implementation.** ~4-5 dev-days vs 2-3 for standard. Uses triplet-based ratio encoding. Only needed for worst-case degraded mode (no bridge at all). Standard approach #1 covers partial degradation since pitch data is available even via UDP fallback.

4. **Timeline: Add at Milestone 7** (Event Detection) — the next milestone modifying the Layer 1A analysis pipeline. Zero disruption to M3-M6 trajectory. Gives 4 milestones of passive fingerprint accumulation before live matching is needed.

### Decision Needed Before M7
- Standard hashing only (approach #1)? Or also generate tempo-invariant hashes (approach #3)?
- If both: add ~2 extra days. Recommend standard first.
- If a full library re-scan is planned before M7, consider a mini-milestone (2-3 days) to avoid needing a second re-scan.

**Full details:** `research/research-findings-audio-fingerprinting-libraries.md`

---

## Cross-Cutting Action Items

| Priority | Item | Scope | Milestone |
|----------|------|-------|-----------|
| **HIGH** | Composite key for `track_ids` table (multi-USB bug) | Schema change + 2 method updates | Current / M3 |
| **HIGH** | `DeckAnalysisState` enum + pending path in TrackCursor | New enum + PlaybackTracker refactor | M3 |
| **MEDIUM** | USB ANLZ waveform reading via pyrekordbox | Extend USB scanner to extract PWAV/PWV3/PWV5 | M3-M4 |
| **MEDIUM** | Stale-scan detection for re-exported USBs | USB identity tracking + metadata comparison | M3-M4 |
| **MEDIUM** | Update ADR-012 to document WaveformFinder exclusion rationale | 1 paragraph | Now |
| **LOW** | Consider re-enabling MetadataFinder for legacy-only hardware | ADR amendment + bridge config | M4+ |
| **LOW** | Constellation-map fingerprint generation | New module + pipeline step | M7 |
| **DEFERRED** | Tempo-invariant hashing (approach #3) | Extension to fingerprint module | M11+ |
| **DEFERRED** | Live fingerprint matching | Query engine + audio capture | M11+ |

---

## Confidence Levels

| Finding | Confidence | Notes |
|---------|:-:|-------|
| WaveformFinder/MetadataFinder hard dependency | HIGH | Direct beat-link source code analysis |
| XDJ-XZ not classified as DLP | HIGH | `DeviceAnnouncement.java` line 61 |
| DLP ID volatility across re-exports | MEDIUM-HIGH | Inferred from DB architecture, not lab-tested |
| Multi-USB collision | HIGH | Mathematical certainty (auto-increment) |
| Hybrid data flow recommendation | HIGH | Existing infrastructure + competitor analysis |
| Fingerprint library assessments | HIGH | GitHub API verified |
| Custom implementation effort (2-3 days) | MEDIUM | Based on algorithm analysis, no prototype |

**Validation recommended:** Test DLP ID stability with a controlled re-export (export same collection twice, compare `content.id` values).
