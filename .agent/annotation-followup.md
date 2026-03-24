# Annotation Tool — Follow-up Items

> Documented from operator feedback after initial implementation (2026-03-24).
> These are NOT implemented yet. The next agent should read this before working on the annotation page.

## Prior work

The ground truth annotation tool was built in a single session. See:
- Plan: `/Users/brach/Documents/THE_FACTORY/.claude/plans/atomic-sniffing-crown.md`
- Backend: `scue/api/ground_truth.py`, `scue/api/audio.py`
- Frontend: `frontend/src/pages/AnnotationPage.tsx`, `frontend/src/components/annotations/`
- Tests: `tests/test_api/test_ground_truth.py` (16 tests)
- Launch configs added to `THE_FACTORY/.claude/launch.json` (scue-backend on 8000, scue-frontend on 5174)

## 1. Beatgrid lines on waveform (APP-GLOBAL)

Add visual indicators overlaid on the waveform showing:
- **Groups of 4 measures** (thickest/most prominent)
- **Individual measures** (medium weight)
- **Quarter-notes within measures** (thinnest/subtlest)

**Adaptive visibility based on zoom level:**
- Zoomed all the way out → only show 4-measure groups
- Medium zoom → show measures + 4-measure groups
- Zoomed in → show quarter-notes + measures (4-measure groups become irrelevant at this scale)

The threshold for showing/hiding each level should be based on pixel density — if the lines would be too close together to be useful, don't render them.

**This is an app-global feature**, not annotation-specific. It should be added to:
- `AnnotationTimeline` (annotation page)
- `WaveformCanvas` (analysis viewer)
- `DeckWaveform` (live monitor)
- Any future waveform component

The operator wants to use these lines to visually assess beatgrid and section boundary accuracy. **Beatgrids come from Pioneer hardware** (via the bridge/USB scan) — that's the source of truth, not SCUE's analysis.

## 2. Pre-populate annotations from detector output

Currently the annotation page starts with an empty annotation list and shows detector output as a faded overlay. The operator wants the **detector predictions loaded as editable annotations by default**, so the workflow is:

- Open a track → annotations are pre-filled from detector output
- Correct what's wrong (move, delete, re-type)
- Add what's missing
- Save

This avoids re-annotating everything the detectors already got right. The "Show detectors" overlay toggle may become less necessary if predictions are the starting annotations, but keep it for A/B comparison.

Implementation note: the pre-population should only happen when no saved ground truth exists for the track. If ground truth is already saved, load that instead (current behavior).

## 3. Track prediction vs correction diff

The operator asks: "Should we be tracking what was originally predicted by our analysis vs how I've corrected it? Is that valuable?"

**Answer: Yes.** This is extremely valuable for:
- Training data: knowing which predictions were confirmed vs corrected tells the eval harness exactly where the detectors fail
- Tuning priority: if 90% of kick predictions are confirmed but only 40% of riser predictions survive correction, you know where to focus
- Regression detection: if a detector config change causes previously-confirmed predictions to now need correction

**Suggested approach:**
- When pre-populating from detector output, tag each annotation with `source: "predicted"`
- When the user modifies or adds an annotation, tag it `source: "corrected"` or `source: "manual"`
- Save the original predictions alongside the ground truth (e.g., `ground_truth/{fp}.json` for final truth, `ground_truth/{fp}.predictions.json` for what the detectors originally output)
- The scoring endpoint can then report not just P/R/F1 but also a correction rate per event type

## 4. Pattern-based annotation (copy/paste drum patterns)

Instead of clicking every kick in a 4-on-the-floor track, the operator wants to:

1. Annotate events within **1 measure or 1 4-measure group**
2. **Copy that pattern** and apply it across the song (or selected sections)
3. **Exclude specific sections** where the pattern deviates (builds, fakeout drops, breakdowns)

This connects to the operator's event taxonomy (4 types):
1. **Song sections** — intro, verse, drop, etc. (already implemented)
2. **Continuous/sustained events** — risers, fallers, sustained synths (have duration)
3. **One-off point events** — individual kicks, snares, stabs
4. **Groups of point events** — drum patterns, arpeggios, fills

The 4th category is the key insight: a "main kick-clap motif" is a **named group of point events within a measure/phrase** that repeats. Summarizing composition becomes: "the main kick-clap motif extends through the entire song except for the build and fakeout drop."

**UX concept:**
- Select a measure or 4-measure region
- Name the pattern (e.g., "main kick-clap")
- "Apply to sections" → select which sections get this pattern
- The pattern stamps out individual events at the correct beat positions
- Edits to the pattern template propagate to all instances (or optionally detach)

This is a significant feature — plan it thoroughly before building.

## 5. Live event display component (APP-GLOBAL)

A UI component that shows, for the currently-playing track:
- **All active sections** the playback cursor is currently inside (e.g., "verse", "drop")
- **Point events as they occur** — flash/highlight kicks, snares, etc. as the song plays through them

This is a **reusable component** for multiple views:
- Annotation page (to verify annotations look right during playback)
- Live deck monitor (to show what's happening in real-time during a DJ set)
- Analysis viewer (to audit section/event accuracy)

Think of it as a "now playing" event feed synced to the audio cursor position.

## Priority ordering (operator's implied priority)

1. ~~Beatgrid lines~~ (DONE — adaptive zoom, 3-tier hierarchy)
2. ~~Pre-populate from detectors~~ (DONE — auto-loads predictions as editable annotations)
3. ~~Prediction vs correction tracking~~ (DONE — source field: predicted/corrected/manual)
4. ~~Live event display component~~ (DONE — useActiveEvents hook + LiveEventDisplay, on annotation + live deck)
5. Pattern-based annotation (largest scope, most design work needed)
