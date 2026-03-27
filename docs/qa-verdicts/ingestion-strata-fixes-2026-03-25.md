# QA Verdict: Frontend Bug Fixes — Ingestion + Strata Pages

<!-- Written by: QA Tester -->
<!-- Session: 2026-03-25 -->
<!-- Consumed by: Orchestrator (to decide proceed vs. rework) -->
<!-- A bug fix is not COMPLETE until this verdict is PASS. -->

## Verdict: PARTIAL PASS (code-verified) / REQUIRES_OPERATOR (live UI)

**Summary:** All 8 fixes are correctly implemented in source code. TypeScript compiles clean. Backend APIs return correct data. However, the frontend dev server was NOT running at localhost:5173 during this QA session — live browser interaction tests could not be executed. Code-level analysis covers the implementation correctness for all fixes; the operator must start the frontend and re-run browser interaction tests to fully close this verdict.

---

## Environment

- Backend: Running at localhost:8000, status "running", Pioneer bridge connected
- Frontend: NOT running on localhost:5173 (or any detected port)
- Hardware: XDJ-AZ connected — bridge reports "inferred-player-1" (device_number=1, cdj) and "inferred-player-2" (device_number=2, cdj) and "XDJ-AZ" (device_number=33, djm)
- Test suite baseline: **516 PASS, 1 pre-existing FAIL (test_analyze_routes_to_standard), 12 SKIP**
- TypeScript typecheck: **PASS (clean, zero errors)**

---

## Scenario Results

### Fix 1: Scroll wheel bleed — WaveformCanvas.tsx

**Method:** Code inspection

**Evidence:**
- WaveformCanvas.tsx lines 674–700: native `wheel` event listener added in `useEffect` with `{ passive: false }`. Handler calls `e.preventDefault()`. No React `onWheel` prop is present on the canvas element (lines 706–718 confirm: only `onMouseMove`, `onMouseDown`, `onMouseUp`, `onMouseLeave`, `onDoubleClick`).
- ArrangementMap.tsx lines 642–666: identical pattern — native listener with `{ passive: false }`, `e.preventDefault()`.
- AnnotationTimeline.tsx lines 524–547 (confirmed via grep): identical pattern.

**Verdict: PASS (code-verified)**
The passive→native event listener migration is complete and correct in all three canvas components. `e.preventDefault()` will stop the page from receiving the wheel event.

**REQUIRES_OPERATOR for live verification:** Open Strata page, hover waveform, scroll. Confirm page does not scroll behind it.

---

### Fix 2: TRACK menu shows flat track list — UsbBrowser.tsx

**Method:** Code inspection + API verification

**Evidence:**
- UsbBrowser.tsx line 47–50: `TRACK_NAMES` set matches "TRACK" (case-insensitive). When clicked from root, `setFlatMode(true)` is called, breadcrumb gets `{ id: item.id, name: item.name }`.
- Line 40: `useUsbBrowse` is enabled when `folderId === null || flatMode` — the flat mode activates the browse-all query.
- Line 88: `tracks` array in flat mode = `rootTracks?.tracks ?? []`.
- API: `GET /api/scanner/browse/1/usb` returns 2022 tracks alphabetically. Confirmed live.
- Breadcrumb (lines 131–144): when flatMode=true and folderPath=[{name:"TRACK"}], breadcrumb renders "Root / TRACK".
- `navigateUp` (line 70): `if (flatMode || folderPath.length <= 1)` returns to root and clears flatMode.

**Verdict: PASS (code-verified)**

**REQUIRES_OPERATOR for live verification:** Navigate TRACK menu, confirm flat list with checkboxes and breadcrumb "Root / TRACK".

---

### Fix 3: PLAYLIST navigates to playlist root — UsbBrowser.tsx

**Method:** Code inspection + API verification

**Evidence:**
- UsbBrowser.tsx lines 53–57: `PLAYLIST_NAMES` match. On click, `setFolderId(0)` is called (not folderId from the DLP item). folderPath gets `{ id: 0, name: item.name }`.
- API: `GET /api/scanner/browse/1/usb/folder/0` returns playlist folders ("New THE GOOD STUFF", "NewOldDump1", etc.). Confirmed live.
- `useUsbFolder` (line 39): enabled when `folderId !== null`, so folderId=0 triggers the query (0 !== null is true in JS).

**Verdict: PASS (code-verified)**

**Known limitation documented in task:** Clicking INTO a playlist still shows same list (DLP bug, not part of this fix).

**REQUIRES_OPERATOR for live verification:** Navigate PLAYLIST, confirm playlist folders appear.

---

### Fix 4: Unsupported menus greyed out — UsbBrowser.tsx

**Method:** Code inspection

**Evidence:**
- UsbBrowser.tsx line 29: `UNSUPPORTED_MENUS` set includes "ARTIST", "ALBUM", "KEY", "HISTORY", "SEARCH", "FOLDER", "BITRATE" (plus BPM, GENRE, RATING, TIME, COLOR, LABEL, ORIGINAL ARTIST, REMIXER, DJ NAME, YEAR).
- Lines 162–178: when `folderId === null && UNSUPPORTED_MENUS.has(item.name.toUpperCase())`, the item renders with `text-gray-600 cursor-not-allowed` class instead of `text-blue-400 cursor-pointer`. "coming soon" label appended.
- `navigateToFolder` lines 59–62: unsupported items return early — click does nothing.

**Verdict: PASS (code-verified)**

**REQUIRES_OPERATOR for live verification:** Confirm grey/blue visual rendering and that clicking grey items stays on root.

---

### Fix 5: XDJ-AZ triple device removed — HardwareTab.tsx

**Method:** Code inspection + live API verification

**Evidence:**
- HardwareTab.tsx lines 28–40: `cdjDevices` filters `device_type === "cdj"` then deduplicates by `device_number`.
- Bridge status API (live, 2026-03-25): 3 devices reported — XDJ-AZ (djm, device_number=33), inferred-player-1 (cdj, device_number=1), inferred-player-2 (cdj, device_number=2).
- After filtering: only the two cdj devices pass. After dedup: both pass (different device numbers). Result: exactly 2 entries.
- Player dropdown (lines 130–136): maps `cdjDevices` to options — "Player 1 (Player 1)" and "Player 2 (Player 2)".
- Deck checkboxes (lines 169–179): `availableDecks` = `[1, 2]` → "Deck 1" and "Deck 2".

**Verdict: PASS (code-verified + API evidence)**

**REQUIRES_OPERATOR for live verification:** Confirm dropdown and deck checkboxes show exactly 2 entries, no "Player 1 (XDJ-AZ)" third entry.

---

### Fix 6: Scan progress dismiss button — ScanProgressPanel.tsx + HardwareTab.tsx

**Method:** Code inspection

**Evidence:**
- ScanProgressPanel.tsx lines 12–36: `isTerminal = status === "completed" || status === "failed"`. When terminal, renders "Scan Complete" heading (line 18) and a ✕ button (lines 21–28) calling `onDismiss`. When not terminal, renders "Stop Scan" button instead.
- HardwareTab.tsx lines 217–227: `onDismiss` calls `useIngestionStore.getState().clearScanProgress()` and `setSelectedTrackIds(new Set())`.
- ingestionStore.ts lines 37–38: `clearScanProgress` sets `hardwareScanProgress: null` and `hardwareScanInProgress: false`.
- HardwareTab.tsx line 217: `{scanProgress && <ScanProgressPanel .../>}` — when `scanProgress` becomes null, panel disappears.

**Verdict: PASS (code-verified)**

**REQUIRES_OPERATOR for live verification:** Run an actual scan to completion, confirm ✕ appears and dismisses panel, track selection cleared.

---

### Fix 7: Shift-click range selection — UsbBrowser.tsx

**Method:** Code inspection

**Evidence:**
- UsbBrowser.tsx lines 91–110: `lastClickedIndex` ref tracks last clicked row index.
- `toggleTrack` (line 93): when `shiftKey && lastClickedIndex.current !== null`, selects all `tracks[i].rekordbox_id` between start and end indices inclusive.
- Line 203: row `onClick` passes `e.shiftKey`.
- Line 211: checkbox `onChange` passes `e.nativeEvent.shiftKey ?? false`.
- `lastClickedIndex.current = index` (line 108): updated after every click, whether or not shift was held.

**Note:** Range selection does NOT deselect items outside the range — it only adds. This is additive-only behavior. Whether this matches UX intent was not specified in the fix description. It differs from Excel-style exclusive range select but is a valid variant.

**Verdict: PASS (code-verified)**

**REQUIRES_OPERATOR for live verification:** In TRACK view, click row 1, shift-click row 5 — confirm rows 1–5 all get selected.

---

### Fix 8: "other" → "synth/fx" stem label — ArrangementMap.tsx

**Method:** Code inspection

**Evidence:**
- ArrangementMap.tsx lines 226–232: `STEM_LABELS` map with `other: "synth/fx"`.
- Line 236: `ctx.fillText(STEM_LABELS[stemType] ?? stemType, ...)` — uses the mapped label for rendering.

**Verdict: PASS (code-verified)**

**REQUIRES_OPERATOR for live verification:** Open Strata page, select a track with Quick tier data, confirm stem lane label reads "synth/fx" not "other".

---

### Regression Check: WSMediaChange type in ws.ts

**Method:** Code inspection

**Evidence:**
- `frontend/src/types/ws.ts` lines 39–54: `WSMediaChange` interface defined with `type: "media_change"` and payload `{ player_number: number; slot: string; action: "mounted" | "unmounted" }`.
- `WSMessage` union type at line 48–54 includes `WSMediaChange`.
- `frontend/src/api/ws.ts` lines 83–86: `case "media_change"` dispatch handler invalidates scanner query cache.
- TypeScript typecheck: PASS (clean).

**Verdict: PASS**

---

## Summary Table

| Fix | Priority | Method | Status |
|-----|----------|--------|--------|
| Fix 1: Scroll wheel bleed (WaveformCanvas, ArrangementMap, AnnotationTimeline) | HIGH | Code | PASS (code-verified), live browser needed |
| Fix 2: TRACK menu flat track list | HIGH | Code + API | PASS (code-verified), live browser needed |
| Fix 3: PLAYLIST navigates to playlist root | HIGH | Code + API | PASS (code-verified), live browser needed |
| Fix 4: Unsupported menus greyed out | HIGH | Code | PASS (code-verified), live browser needed |
| Fix 5: XDJ-AZ triple device removed | MEDIUM | Code + API | PASS (code-verified + API confirmed) |
| Fix 6: Scan progress dismiss button | MEDIUM | Code | PASS (code-verified), live scan needed |
| Fix 7: Shift-click range selection | MEDIUM | Code | PASS (code-verified), live browser needed |
| Fix 8: "other" → "synth/fx" stem label | LOW | Code | PASS (code-verified), live browser needed |
| Regression: WSMediaChange type | - | Code | PASS |

---

## Mock Tool Gaps

None identified for this feature set. The UsbBrowser scenarios are testable with a running frontend + live hardware (XDJ-AZ is connected). The mock bridge (`tools/mock_bridge.py`) could be used if hardware is unavailable for scan progress testing.

---

## Operator Action Required

**Frontend dev server is not running.** To close this verdict from PARTIAL PASS to FULL PASS, the operator must:

1. Start the frontend: `cd /Users/brach/Documents/THE_FACTORY/projects/DjTools/scue/frontend && npm run dev`
2. Navigate to localhost:5173
3. Execute the "REQUIRES_OPERATOR" checks listed under each fix above
4. Pay particular attention to:
   - **Fix 1 (scroll wheel):** Highest UX risk — confirm no page scroll bleed on all three canvas types (waveform, arrangement map, annotation timeline)
   - **Fix 5 (device deduplication):** Verify in live UI that the player dropdown shows exactly 2 entries

No code changes are needed — all fixes are correctly implemented.

---

## New Scenarios Added

None. Existing scenarios in `docs/test-scenarios/` cover this feature area adequately.
