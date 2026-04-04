---
status: COMPLETE
project_root: /Users/brach/Documents/THE_FACTORY/projects/DjTools/scue
revision_of: none
supersedes: none
superseded_by: none
---

# QA Verdict: Self-Contained Analysis Tiers — Static Frontend Review

## Verdict: FAIL

One BLOCKING regression found in the backend test suite introduced by the same feature
changeset. Frontend static analysis passes with no issues found.

## Environment
- Server: n/a (static code review + TypeScript typecheck + pytest)
- Hardware: n/a
- Browser: n/a

---

## Scenarios Executed

| Scenario | Status | Notes |
|----------|--------|-------|
| SC-001: Stale state identifiers removed from ScueLibraryTab | PASS | Zero matches for all removed identifiers |
| SC-002: Removed import from ../../api/analyze | PASS | No such import present |
| SC-003: Bulk actions bar gating | PASS | Tier picker renders for all selectedTracks.size > 0 |
| SC-004: fingerprintsToAnalyze uses selectedTrackData directly | PASS | No version > 0 filter; filters only by tier has_* field |
| SC-005: Run button disabled state | PASS | References batchMutation.isPending + batchId + length; no isAudioJobRunning |
| SC-006: BASE_PLUS_TIER_DURATIONS steps 1-15 | PASS | All 15 entries present, correctly weighted |
| SC-007: durationWeightedPercent accepts needsBase | PASS | Third parameter with default false |
| SC-008: estimateRemaining accepts needsBase | PASS | Third parameter with default false |
| SC-009: phaseLabel returns "Analyzing audio..." for base phase | PASS | Correct conditional on needs_base && phase === "base" |
| SC-010: StrataJobStatus has needs_base, phase, title | PASS | All three fields present with correct types |
| SC-011: StrataBatchProgress per-track collapsible list | PASS | Collapsible rendered when batch.jobs.length > 1 |
| SC-012: Phase-aware labels in per-track list | PASS | "audio" label for base phase, tier name otherwise |
| SC-013: Null/undefined safety — batch fields | PASS | needs_base, phase, title all non-optional on StrataJobStatus; no undefined access risk for in-flight jobs IF backend sends all fields |
| SC-014: TypeScript typecheck | PASS | tsc --noEmit exits 0, zero errors |
| SC-015: Backend test regression check | FAIL | 3 tests fail — see Failures section |

---

## Failures

### SC-015: Backend test regression — progress_callback signature mismatch

- **Expected:** All pre-existing backend tests pass with the new changeset applied.
- **Observed:** 3 tests fail with a mock assertion mismatch. The strata engine's
  `analyze_quick` and `analyze_standard` methods were updated to accept a
  `progress_callback` keyword argument, but the corresponding unit test mocks
  were not updated to expect it. This causes `assert_called_with()` to fail
  because the actual call now includes `progress_callback=None` while the
  expected call does not.

  ```
  AssertionError: expected call not found.
  Expected: analyze_standard('abc123', analysis_version=None)
    Actual: analyze_standard('abc123', analysis_version=None, progress_callback=None)
  ```

  Failing tests:
  - `tests/test_layer1/test_strata_hybrid.py::TestHybridTierValidation::test_hybrid_requires_track_analysis`
  - `tests/test_layer1/test_strata_standard.py::TestEngineRouting::test_analyze_routes_to_quick`
  - `tests/test_layer1/test_strata_standard.py::TestEngineRouting::test_analyze_routes_to_standard`

  Confirmed pre-existing: running these same tests on a stashed working tree
  (prior to current changes) passes all 3. The regression is introduced by
  the current changeset (`scue/layer1/strata/engine.py`).

- **Logs:** Consistent across all 3 failures; mock expects old signature, actual
  call matches new signature with `progress_callback=None`.
- **Severity:** BLOCKING — the test suite reports failures that must be fixed
  before the feature can be merged cleanly. The production behavior is likely
  correct (the parameter is wired up), but the tests are broken.

---

## Findings: Notable but not blocking

### F-01: StrataJobProgress uses setTimeout for onComplete (cosmetic risk)

In `StrataJobProgress` (the single-track variant, not the batch variant), the
`onComplete` callback is scheduled via `setTimeout(onComplete, 0)` at render time
(line 123):

```typescript
if (isDone && onComplete) {
  setTimeout(onComplete, 0);
}
```

This is called on every render while `isDone` is true, which means if the parent
re-renders before unmounting the component, `onComplete` fires multiple times.
The batch component (`StrataBatchProgress`) correctly uses a `useRef` guard
(`completeFired`) to prevent this. The single-track component does not, and will
fire `onComplete` on every re-render after completion.

The `StrataJobProgress` component is not used in the `ScueLibraryTab` path (only
`StrataBatchProgress` is), so this does not block the current feature. It is a
latent bug in the Analysis page if `StrataJobProgress` is used there with an
`onComplete` callback.

**Severity:** COSMETIC for the current feature scope. DEGRADED if onComplete
causes cache invalidation or state mutation in a caller that uses `StrataJobProgress`.

### F-02: Backward compat of StrataJobStatus fields with in-flight jobs

`needs_base`, `phase`, and `title` are declared as non-optional in `StrataJobStatus`.
If a job was started with an older backend that does not send these fields, the
TypeScript types will lie — the runtime values will be `undefined`, and the
`phaseLabel` guard (`job.needs_base && job.phase === "base"`) will evaluate to
`false` gracefully. `job.title` usage falls back to `job.fingerprint.slice(0, 16)`
via the `||` operator. No crash risk in practice, but the types do not reflect the
true runtime contract during a rolling deploy. Acceptable for a non-production
system; document if the backend ever does rolling upgrades.

**Severity:** COSMETIC.

---

## Regression Check

- 706 tests pass. 3 tests that were previously passing now fail due to the
  `progress_callback` signature change in the strata engine. This is a regression
  introduced by the current changeset. All frontend-related static checks pass.

---

## Mock Tool Gaps

All executed scenarios were static code review and TypeScript typecheck. No live
server or hardware interaction was required. No mock gaps.

---

## Recommendation

1. **Fix the 3 failing backend tests before merging.** In each test that mocks
   `analyze_quick` or `analyze_standard`, update the `assert_called_with()` to
   include `progress_callback=ANY` (using `unittest.mock.ANY`) or switch to
   `assert_called_once()` plus separate argument assertions. This is a two-line
   fix per test.

2. **Fix the setTimeout multi-fire in StrataJobProgress.** Add a `useRef` guard
   identical to the one in `StrataBatchProgress`. The fix is low-risk and prevents
   a subtle bug from appearing when the Analysis page wires up an `onComplete`
   handler to `StrataJobProgress`.

3. After both fixes, re-run `pytest tests/` and `npm run typecheck`. A clean run
   on both gives a PASS verdict for this feature.
