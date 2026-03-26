# Pending Verification — Cross-Session Handoffs

Items that need live verification but couldn't be verified in the session that built them.

---

## Strata Reanalysis UI + Source Comparison

**Date:** 2026-03-24
**Built in:** opus session (strata-reanalysis)

### Requires
- Pioneer hardware connected (XDJ-AZ or CDJ via USB-Ethernet)
- At least one track analyzed offline (v1 exists in `tracks/`)
- Track loaded on Pioneer deck so enrichment pass runs (produces v2)

### Setup Steps
1. Start backend: `uvicorn scue.main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Connect Pioneer hardware, load a track on a deck
4. Wait for enrichment pass to run (check logs for "Enrichment complete")
5. Navigate to `/strata` page

### What to Verify

**Reanalyze button:**
1. Select the enriched track in the track picker
2. A teal "Re-analyze (Pioneer Grid)" button should appear (only when v2 exists and v3 doesn't)
3. Click it — should trigger background reanalysis (~5-10s)
4. After completion, the button should disappear (v3 now exists)
5. Verify via `GET /api/tracks/{fp}/versions` — should show v1, v2, v3

**Source selector:**
1. Run Strata quick analysis on the track: click "Analyze Quick"
2. Then run it again targeting the reanalyzed version: `POST /api/tracks/{fp}/strata/analyze` with `{"tiers": ["quick"], "analysis_source": "pioneer_reanalyzed"}`
3. The tier selector area should show "Source: Original | Reanalyzed" buttons
4. Switching between them should show different formula data (sections may differ due to re-snapping)

**Comparison mode:**
1. With both sources available, switch to Compare mode
2. Should be able to compare Quick(Original) vs Quick(Reanalyzed) side by side
3. Diff indicators should show section/pattern/transition differences

### Expected Results
- v3 sections should differ from v2 (re-snapped to Pioneer downbeat grid, not just timestamp-scaled)
- v3 events should differ from v2 (re-detected with Pioneer beats, not just scaled)
- Strata results from v1 vs v3 should show measurable differences in section boundaries and pattern counts

### Files to Check if Issues
- `scue/layer1/reanalysis.py` — the reanalysis pass
- `scue/api/strata.py` — endpoints (especially `/reanalyze`, `/versions`)
- `frontend/src/pages/StrataPage.tsx` — source selector + reanalyze button logic
- `scue/layer1/strata/storage.py` — source-qualified file paths
