# Handoff: Bridge Finder Upgrade — beat-link 8.1.0-SNAPSHOT

---
status: APPROVED
project_root: /Users/brach/Documents/THE_FACTORY/projects/DjTools/scue
---

## Objective

Upgrade the beat-link bridge from v8.0.0 to v8.1.0-SNAPSHOT and enable all Finders
(MetadataFinder, WaveformFinder, BeatGridFinder, AnalysisTagFinder, CrateDigger) so that
SCUE receives live metadata, waveforms, beatgrids, phrase analysis, and cue points from
Pioneer hardware — including DLP devices like the XDJ-AZ.

This supersedes ADR-012's blanket Finder disabling. beat-link 8.1.0-SNAPSHOT has native
XDJ-AZ support via CrateDigger NFS downloads and SQLite ID translation.

**Four sequential tasks, all in this session.**

## Context

Read these files before writing any code:

1. `CLAUDE.md` — project rules
2. `LEARNINGS.md` — known issues
3. `research/beatlink-dlp-fix-investigation.md` — full bug trace + fix strategy (READ ALL)
4. `docs/bridge-java-spec.md` — current bridge spec
5. `docs/DECISIONS.md` — ADR-012, ADR-013 (being superseded)
6. `skills/beat-link-bridge.md` — bridge domain knowledge
7. `bridge-java/src/main/java/com/scue/bridge/BeatLinkBridge.java` — current bridge
8. `bridge-java/src/main/java/com/scue/bridge/MessageEmitter.java` — current emitter
9. `bridge-java/build.gradle` — current dependencies
10. `scue/bridge/messages.py` — Python message types (already has all payload types defined!)
11. `scue/bridge/adapter.py` — Python adapter (already has handlers for all message types!)

**Critical insight:** The Python side already has message types and adapter handlers for
`track_metadata`, `waveform_detail`, `beat_grid`, `phrase_analysis`, and `cue_points`.
They were defined in anticipation of future bridge extensions. The adapter already handles
them — it just never receives them because the Java bridge doesn't emit them yet.

## Role
Developer

## Task Sequence

Complete these four tasks **in order**. Build the bridge JAR after TASK-001 and TASK-002.
Run Python tests after TASK-003. Do not begin the next task until the current one passes.

---

### TASK-001: Upgrade beat-link dependency and enable Finders

**Goal:** Bump beat-link from 8.0.0 to 8.1.0-SNAPSHOT. Enable MetadataFinder, WaveformFinder,
BeatGridFinder, AnalysisTagFinder, and CrateDigger in the bridge startup. Add `--database-key`
CLI argument.

**Files to modify:**
- `bridge-java/build.gradle`
- `bridge-java/src/main/java/com/scue/bridge/BeatLinkBridge.java`

**Changes to `build.gradle`:**

1. Add the Sonatype snapshots repository (beat-link SNAPSHOTs are published there):
```groovy
repositories {
    mavenCentral()
    maven {
        url 'https://s01.oss.sonatype.org/content/repositories/snapshots/'
    }
}
```

2. Change beat-link version:
```groovy
implementation 'org.deepsymmetry:beat-link:8.1.0-SNAPSHOT'
```

**Changes to `BeatLinkBridge.java`:**

1. **Add imports** for the new beat-link classes:
```java
import org.deepsymmetry.beatlink.data.*;
```

2. **Add `--database-key` CLI argument** (in `main()` switch statement):
```java
case "--database-key":
    if (i + 1 < args.length) databaseKey = args[++i];
    break;
```
Pass `databaseKey` to the `BeatLinkBridge` constructor. Store it as an instance field.

3. **Add `configureOpusProvider()` method** — call this BEFORE starting Finders:
```java
private void configureOpusProvider() {
    if (databaseKey != null && !databaseKey.isEmpty()) {
        OpusProvider.getInstance().setDatabaseKey(databaseKey);
        log.info("DLP database key configured — exportLibrary.db decryption enabled");
    }
}
```

4. **Add `startFinders()` method** — call this in `initBeatLink()` AFTER BeatFinder starts
   and AFTER `configureOpusProvider()`:
```java
private void startFinders() {
    try {
        // Configure DLP database key before starting any Finders
        configureOpusProvider();

        // Start TimeFinder first (required by waveform position tracking)
        TimeFinder.getInstance().start();
        log.info("TimeFinder started");

        // Start MetadataFinder (required by WaveformFinder)
        MetadataFinder.getInstance().start();
        log.info("MetadataFinder started");

        // Start remaining Finders
        BeatGridFinder.getInstance().start();
        log.info("BeatGridFinder started");

        WaveformFinder.getInstance().start();
        log.info("WaveformFinder started");

        AnalysisTagFinder.getInstance().start();
        log.info("AnalysisTagFinder started");

        // Start ArtFinder for album artwork
        ArtFinder.getInstance().start();
        log.info("ArtFinder started");

        log.info("All Finders started successfully");
    } catch (Exception e) {
        log.error("Failed to start Finders: {}. Bridge will continue with real-time data only.", e.getMessage(), e);
    }
}
```

5. **Update `initBeatLink()`** — call `startFinders()` after `registerListeners()`:
```java
registerListeners();
startFinders();        // NEW — enable metadata/waveform/beatgrid/phrase/cue
registerFinderListeners();  // NEW — see TASK-002
```

6. **Update `cleanupBeatLink()`** — stop Finders on cleanup:
```java
private void cleanupBeatLink() {
    try { ArtFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
    try { AnalysisTagFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
    try { WaveformFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
    try { BeatGridFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
    try { MetadataFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
    try { TimeFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
    try { BeatFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
    try { if (VirtualCdj.getInstance().isRunning()) VirtualCdj.getInstance().stop(); } catch (Exception e) { /* ignore */ }
    try { if (DeviceFinder.getInstance().isRunning()) DeviceFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
}
```

7. **Update `shutdown()`** — stop Finders before BeatFinder.

8. **Update `registerListeners()` log message** — remove "no metadata finders" text.

9. **Update bridge `VERSION`** to `"2.0.0"`.

**Done when:**
- [ ] `build.gradle` uses beat-link 8.1.0-SNAPSHOT with snapshot repo
- [ ] `--database-key` CLI argument parsed and stored
- [ ] `OpusProvider.setDatabaseKey()` called when key is provided
- [ ] All 6 Finders start in correct order (TimeFinder → MetadataFinder → rest)
- [ ] Finders stopped on cleanup and shutdown
- [ ] Bridge version bumped to 2.0.0
- [ ] `./gradlew shadowJar` builds successfully

---

### TASK-002: Add Finder message types to the Java bridge

**Goal:** Register listeners for MetadataFinder, WaveformFinder, BeatGridFinder,
AnalysisTagFinder, and ArtFinder. Emit new message types over WebSocket when track data
arrives or changes.

**Files to modify:**
- `bridge-java/src/main/java/com/scue/bridge/BeatLinkBridge.java`
- `bridge-java/src/main/java/com/scue/bridge/MessageEmitter.java`

**New message types to emit:**

#### `track_metadata`
Emitted when MetadataFinder resolves metadata for a track change.

```json
{
  "type": "track_metadata",
  "timestamp": 1710600021.0,
  "player_number": 1,
  "payload": {
    "title": "Gimme! Gimme! Gimme! (A Man After Midnight)",
    "artist": "ABBA",
    "album": "Greatest Hits Vol. 2",
    "genre": "Pop",
    "key": "Dm",
    "bpm": 120.0,
    "duration": 287.5,
    "color": null,
    "rating": 0,
    "comment": "",
    "rekordbox_id": 42001
  }
}
```

Source: `MetadataFinder.TrackMetadataListener.metadataChanged(TrackMetadataUpdate)`
- `update.metadata.getTitle()`, `.getArtist()`, `.getAlbum()`, `.getGenre()`
- `.getKey().label` for key string
- `.getTempo() / 100.0` for BPM
- `.getDuration()` for seconds
- `.getComment()`, `.getRating()`, `.getColor()`

#### `beat_grid`
Emitted when BeatGridFinder resolves a beat grid.

```json
{
  "type": "beat_grid",
  "timestamp": 1710600021.0,
  "player_number": 1,
  "payload": {
    "beats": [
      { "beat_number": 1, "time_ms": 450.0, "bpm": 120.0 },
      { "beat_number": 2, "time_ms": 950.0, "bpm": 120.0 }
    ]
  }
}
```

Source: `BeatGridFinder.BeatGridListener.beatGridChanged(BeatGridUpdate)`
- Iterate `update.beatGrid.beatCount` entries
- For each beat: `.getTimeWithinTrack(beatNumber)` for time_ms, `.getBpm()` for tempo

**Note:** Beat grids can have thousands of entries. Send all of them — the Python side
will store them. For a 5-minute track at 128 BPM, that's ~640 beats. Under 50KB as JSON.

#### `waveform_detail`
Emitted when WaveformFinder resolves waveform data.

```json
{
  "type": "waveform_detail",
  "timestamp": 1710600021.0,
  "player_number": 1,
  "payload": {
    "data": "<base64-encoded waveform bytes>",
    "total_beats": 640
  }
}
```

Source: `WaveformFinder.WaveformListener.detailChanged(WaveformDetailUpdate)`
- `update.detail.getData()` returns `ByteBuffer`
- Base64-encode the raw bytes for transport
- `total_beats`: beat count from the corresponding beat grid

**Also emit `waveform_preview`** using same shape when preview data arrives:
- `WaveformFinder.WaveformListener.previewChanged(WaveformPreviewUpdate)`

#### `phrase_analysis`
Emitted when AnalysisTagFinder resolves PSSI (song structure) data.

```json
{
  "type": "phrase_analysis",
  "timestamp": 1710600021.0,
  "player_number": 1,
  "payload": {
    "phrases": [
      { "start_beat": 1, "end_beat": 33, "kind": "intro", "mood": 1 },
      { "start_beat": 33, "end_beat": 97, "kind": "verse", "mood": 1 }
    ]
  }
}
```

Source: `AnalysisTagFinder.AnalysisTagListener.analysisChanged(AnalysisTagUpdate)`
- Filter for tag type `".EXT"` and name `"PSSI"`
- Cast body to `RekordboxAnlz.SongStructureTag`
- Iterate `.body().entries()`: each `SongStructureEntry` has `.beat()` (start beat),
  `.kind()` (phrase type enum), `.fill()`, `.beatFill()`
- `end_beat` = next entry's `.beat()` (or total beats for last entry)
- `kind`: map the enum to string — use `Util.phraseLabel(entry)` if available

#### `cue_points`
Emitted when MetadataFinder resolves cue list data.

```json
{
  "type": "cue_points",
  "timestamp": 1710600021.0,
  "player_number": 1,
  "payload": {
    "cue_points": [
      { "time_ms": 0.0, "name": "", "color": "" }
    ],
    "memory_points": [
      { "time_ms": 45230.0, "name": "Drop", "color": "#FF0000" }
    ],
    "hot_cues": [
      { "slot": 1, "time_ms": 0.0, "name": "A", "color": "#00FF00" }
    ]
  }
}
```

Source: `TrackMetadata.getCueList()` (available in the metadata listener callback)
- Iterate cue entries, classify by type (hot cue vs memory)
- `.getTimeOffset()` for time_ms, `.getLabel()` for name

**Changes to `MessageEmitter.java`:**

Add emit methods for each new message type. Follow the existing pattern — each method
takes specific parameters, builds a payload Map, calls `emit(type, playerNumber, payload)`.

**Changes to `BeatLinkBridge.java`:**

Add `registerFinderListeners()` method called after `startFinders()`:

```java
private void registerFinderListeners() {
    // Metadata listener
    MetadataFinder.getInstance().addTrackMetadataListener(update -> {
        try {
            if (update.metadata != null) {
                emitTrackMetadata(update.player, update.metadata);
            }
        } catch (Exception e) {
            log.error("Error in metadata listener: {}", e.getMessage(), e);
        }
    });

    // Beat grid listener
    BeatGridFinder.getInstance().addBeatGridListener(update -> {
        try {
            if (update.beatGrid != null) {
                emitBeatGrid(update.player, update.beatGrid);
            }
        } catch (Exception e) {
            log.error("Error in beat grid listener: {}", e.getMessage(), e);
        }
    });

    // Waveform listeners (preview + detail)
    WaveformFinder.getInstance().addWaveformListener(new WaveformListener() {
        @Override
        public void previewChanged(WaveformPreviewUpdate update) {
            try {
                if (update.preview != null) {
                    emitWaveformPreview(update.player, update.preview);
                }
            } catch (Exception e) {
                log.error("Error in waveform preview listener: {}", e.getMessage(), e);
            }
        }
        @Override
        public void detailChanged(WaveformDetailUpdate update) {
            try {
                if (update.detail != null) {
                    emitWaveformDetail(update.player, update.detail);
                }
            } catch (Exception e) {
                log.error("Error in waveform detail listener: {}", e.getMessage(), e);
            }
        }
    });

    // Phrase analysis (PSSI) listener
    AnalysisTagFinder.getInstance().addAnalysisTagListener(
        (player, slot, rekordboxId, section) -> {
            try {
                emitPhraseAnalysis(player, section);
            } catch (Exception e) {
                log.error("Error in analysis tag listener: {}", e.getMessage(), e);
            }
        },
        ".EXT", "PSSI"
    );

    log.info("Finder listeners registered (metadata, beatgrid, waveform, phrase, cues)");
}
```

**Important API notes:**
- `TrackMetadataUpdate` has `.player` (int) and `.metadata` (`TrackMetadata` or null)
- `BeatGridUpdate` has `.player` (int) and `.beatGrid` (`BeatGrid` or null)
- `WaveformPreviewUpdate` / `WaveformDetailUpdate` have `.player` and `.preview`/`.detail`
- `AnalysisTagListener` takes a lambda `(int player, SlotReference slot, int rekordboxId, TaggedSection section)`
- Filter for null values — Finders emit null when a track is unloaded
- Wrap ALL listener callbacks in try-catch to prevent one exception from killing the listener thread

**Method signatures for helper methods in BeatLinkBridge:**

```java
private void emitTrackMetadata(int player, TrackMetadata metadata) { ... }
private void emitBeatGrid(int player, BeatGrid beatGrid) { ... }
private void emitWaveformPreview(int player, WaveformPreview preview) { ... }
private void emitWaveformDetail(int player, WaveformDetail detail) { ... }
private void emitPhraseAnalysis(int player, TaggedSection section) { ... }
```

These call the corresponding `emitter.emitXxx()` methods after extracting data from
beat-link objects.

**Done when:**
- [ ] `MessageEmitter` has emit methods for all 5 new message types
- [ ] `registerFinderListeners()` registers listeners for all Finders
- [ ] All listeners wrapped in try-catch
- [ ] Null checks for unloaded tracks
- [ ] `./gradlew shadowJar` builds successfully
- [ ] Copy built JAR to `lib/beat-link-bridge.jar`

---

### TASK-003: Update Python bridge adapter and spec docs

**Goal:** Verify the Python adapter handles new message types correctly. Update bridge spec
and ADRs. Add `--database-key` to bridge manager startup.

**Files to modify:**
- `scue/bridge/manager.py` — add `database_key` parameter to bridge startup command
- `scue/bridge/adapter.py` — verify handlers work (they should already — check edge cases)
- `docs/bridge-java-spec.md` — update to reflect Finders are enabled, new message types, version 2.0.0
- `docs/DECISIONS.md` — add ADR-017 superseding ADR-012
- `docs/bridge/PITFALLS.md` — update MetadataFinder entry

**Files to read (not modify):**
- `scue/bridge/messages.py` — verify payload types match what Java bridge now emits
- `scue/bridge/adapter.py` — verify handlers are correct

**Changes to `manager.py`:**

Find where the bridge JAR is launched (likely a subprocess command). Add `--database-key`
to the command line if a database key is configured. The database key should come from
SCUE's configuration — check `scue/config/loader.py` for where to add it, or accept it
via an environment variable `SCUE_DLP_DATABASE_KEY`.

**Changes to `adapter.py`:**

The adapter already has handlers for `track_metadata`, `beat_grid`, `waveform_detail`,
`phrase_analysis`, and `cue_points` (lines 266-358). Verify:

1. `_handle_track_metadata()` — check that it fires `on_track_loaded` callback correctly.
   Currently it fires when `payload.title != old_title`. This should also fire when
   `payload.rekordbox_id != player.rekordbox_id` (in case title is the same but it's a
   different track with same title).

2. `_handle_waveform_detail()` — currently only sets `player.has_waveform = True`.
   The waveform `data` field (base64 bytes) should be stored on `PlayerState` so the
   frontend can access it. Add `waveform_data: str = ""` to `PlayerState` and populate it.

3. `_handle_beat_grid()` — looks correct. Stores beats as list of dicts.

4. `_handle_phrase_analysis()` — looks correct. Stores phrases as list of dicts.

5. `_handle_cue_points()` — looks correct. Stores cue_points, memory_points, hot_cues.

**ADR-017: Enable beat-link Finders via 8.1.0-SNAPSHOT upgrade (supersedes ADR-012)**

Write this ADR in `docs/DECISIONS.md`:

```
## ADR-017: Enable beat-link Finders via 8.1.0-SNAPSHOT upgrade
Date: 2026-03-20
Status: SUPERSEDES ADR-012
Context: Research confirmed beat-link 8.1.0-SNAPSHOT (used by BLT) has native XDJ-AZ support.
The XDJ-AZ has a working dbserver (unlike Opus Quad). CrateDigger downloads exportLibrary.db
via NFS, providing ID translation. All Finders work correctly. ADR-012's blanket disabling
was correct for 8.0.0 but is no longer needed.
Decision: Upgrade bridge from beat-link 8.0.0 to 8.1.0-SNAPSHOT. Enable MetadataFinder,
WaveformFinder, BeatGridFinder, AnalysisTagFinder, CrateDigger, TimeFinder, and ArtFinder.
Add --database-key CLI argument for DLP database decryption (required for exportLibrary.db).
Retain rbox/pyrekordbox USB scanning as supplementary source (offline analysis, pre-scan
before hardware is connected). Bridge version bumped to 2.0.0.
Consequences: Bridge now emits track_metadata, beat_grid, waveform_detail, phrase_analysis,
and cue_points messages. Python adapter already handles these. Database key must be configured
for DLP hardware. Opus Quad still requires metadata archives (no dbserver).
```

**Update `docs/bridge-java-spec.md`:**
- Update overview paragraph: remove "real-time playback data only" language
- Update "Not started (per ADR-012)" → "All Finders enabled (ADR-017)"
- Add new message type schemas
- Update version references to 2.0.0
- Add `--database-key` to CLI arguments table
- Update beat-link API entry points table to include all Finder classes

**Update `docs/bridge/PITFALLS.md`:**
- Update the MetadataFinder pitfall entry: add note that 8.1.0-SNAPSHOT resolves the issue
- Add pitfall: "Database key required for DLP database decryption on XDJ-AZ"

**Done when:**
- [ ] `manager.py` passes `--database-key` to bridge subprocess when configured
- [ ] `adapter.py` waveform handler stores `waveform_data` on `PlayerState`
- [ ] `adapter.py` metadata handler fires `on_track_loaded` on rekordbox_id change (not just title)
- [ ] ADR-017 written in `docs/DECISIONS.md`
- [ ] `docs/bridge-java-spec.md` updated for v2.0.0
- [ ] `docs/bridge/PITFALLS.md` updated
- [ ] `.venv/bin/python -m pytest tests/test_bridge/` passes

---

### TASK-004: Update mock bridge and add integration test fixtures

**Goal:** Update `tools/mock_bridge.py` to emit the new message types so frontend development
can proceed without hardware. Add test fixtures for the new message types.

**Files to modify:**
- `tools/mock_bridge.py` — add mock emissions for track_metadata, beat_grid, waveform_detail, phrase_analysis, cue_points
- `tests/fixtures/bridge/` — add fixture JSON files for new message types

**Changes to `mock_bridge.py`:**

After emitting `player_status` for a simulated track load, also emit:
1. `track_metadata` — with realistic title/artist/BPM data
2. `beat_grid` — generate a uniform grid (e.g., 128 BPM, 500ms between beats)
3. `waveform_detail` — base64-encode a synthetic waveform (can be random bytes for now)
4. `phrase_analysis` — generate 3-4 phrases (intro → verse → chorus → outro)
5. `cue_points` — generate 2-3 hot cues and memory points

Emit these with a small delay after `player_status` (simulating Finder resolution time):
```python
await asyncio.sleep(0.5)  # Simulate Finder query latency
```

**Test fixtures:**

Create fixture files in `tests/fixtures/bridge/` matching the new message schemas:
- `track_metadata.json`
- `beat_grid.json`
- `waveform_detail.json`
- `phrase_analysis.json`
- `cue_points.json`

These should be valid message envelopes that can be parsed by `messages.parse_message()`.

**Done when:**
- [ ] `mock_bridge.py` emits all 5 new message types on simulated track loads
- [ ] Fixture files exist for all 5 message types
- [ ] `.venv/bin/python -m pytest tests/test_bridge/` passes
- [ ] Running `python tools/mock_bridge.py` and connecting shows new messages in log

---

## Scope Boundary

**Files this agent MAY modify:**
- `bridge-java/build.gradle`
- `bridge-java/src/main/java/com/scue/bridge/BeatLinkBridge.java`
- `bridge-java/src/main/java/com/scue/bridge/MessageEmitter.java`
- `scue/bridge/adapter.py` — only to fix waveform storage and metadata callback
- `scue/bridge/manager.py` — only to add `--database-key` passthrough
- `tools/mock_bridge.py`
- `tests/fixtures/bridge/`
- `tests/test_bridge/`
- `docs/bridge-java-spec.md`
- `docs/DECISIONS.md` — only to add ADR-017
- `docs/bridge/PITFALLS.md`

**Files this agent MAY read (not modify):**
- `scue/bridge/messages.py`
- `scue/bridge/client.py`
- `scue/config/loader.py`
- `research/beatlink-dlp-fix-investigation.md`
- `skills/beat-link-bridge.md`

**Files this agent must NOT touch:**
- `scue/layer1/` — all Layer 1 files
- `scue/api/` — all API files
- `frontend/` — all frontend files
- `scue/bridge/messages.py` — message types are already correct
- `scue/bridge/fallback.py`
- `docs/interfaces.md` — no contract changes needed (message types already defined)

## Constraints

- Complete tasks in order: TASK-001 → TASK-002 → TASK-003 → TASK-004
- Build the JAR after TASK-002: `cd bridge-java && ./gradlew shadowJar`
- Copy built JAR: `cp bridge-java/build/libs/beat-link-bridge.jar lib/beat-link-bridge.jar`
- Run Python tests after TASK-003: `.venv/bin/python -m pytest tests/test_bridge/`
- If the Sonatype snapshot repo URL is wrong or beat-link 8.1.0-SNAPSHOT isn't found, check
  `https://s01.oss.sonatype.org/content/repositories/snapshots/org/deepsymmetry/beat-link/`
  for the correct path. Alternative: `https://oss.sonatype.org/content/repositories/snapshots/`
- Do NOT change the message envelope format (type, timestamp, player_number, payload)
- Do NOT add new Python dependencies
- Wrap ALL Java listener callbacks in try-catch — an exception must never kill a listener thread
- If a Finder fails to start, log the error and continue — the bridge should still provide
  real-time data even if Finders are unavailable
- `[INTERFACE IMPACT]` — flag and stop if changes would affect `docs/interfaces.md`

## Acceptance Criteria (session-level)

- [ ] Bridge JAR builds with beat-link 8.1.0-SNAPSHOT
- [ ] All 6 Finders start on bridge startup (with --database-key)
- [ ] Bridge emits track_metadata, beat_grid, waveform_detail, phrase_analysis, cue_points
- [ ] Python adapter handles all new message types
- [ ] PlayerState accumulates metadata, beatgrid, phrases, cues, waveform data
- [ ] Mock bridge emits new message types for frontend development
- [ ] All Python tests pass
- [ ] ADR-017 written, bridge spec updated, pitfalls updated

## Dependencies

- Requires: beat-link 8.1.0-SNAPSHOT available on Maven/Sonatype
- Blocks: feat-FE-live-deck-monitor (frontend Player Status UI)
- Related: feat-DLP-namespace-fix (composite key — independent, can be done in parallel)

## Open Questions

1. **Snapshot stability:** 8.1.0-SNAPSHOT may have breaking changes before release. If the
   build fails with API incompatibilities, document the specific failures and stop. Do not
   attempt to fix beat-link source.

2. **Database key source:** Where should the DLP database key be stored in SCUE config?
   For now, pass via environment variable `SCUE_DLP_DATABASE_KEY`. A config file option
   can be added later.

3. **Waveform data size:** Color waveform detail for a 5-minute track is ~150KB base64.
   This is fine for WebSocket transport (well under typical frame limits). If performance
   issues arise, waveform can be sent as binary WebSocket frame instead.
