# Research Findings: Audio Fingerprinting Library Options & Timeline

## Questions Addressed
1. What Python libraries exist for constellation-map audio fingerprinting? Evaluate suitability for SCUE.
2. Would adding minimal fingerprint generation (offline only) to the analysis pipeline be low-cost?
3. Are there existing implementations of tempo-invariant hashing (approach #3)?
4. Is there a natural insertion point earlier than Milestone 11?

## Findings

### Question 1: Python Library Comparison

**Answer:** Four libraries were evaluated. None are a perfect fit. audfprint is the closest to SCUE's needs (pure Python, constellation-map, file-based DB, MIT license) but is unmaintained. Chromaprint/pyacoustid is actively maintained but uses a fundamentally different algorithm (chroma-based, not constellation-map) and depends on an external C library and the AcoustID web service. dejavu implements constellation maps but requires MySQL/PostgreSQL. The most practical path for SCUE is a custom implementation (~500-800 lines) using librosa features already in the pipeline.

**Library Comparison Table:**

| Library | Last Commit | Py 3.11+ | Algorithm | Tempo Handling | DB Backend | License | SCUE Fit |
|---|---|---|---|---|---|---|---|
| **dejavu** (worldveil/dejavu) | 2020-06 | Unlikely (pinned numpy 1.17, scipy 1.3) | Constellation map (Shazam-style) | None | MySQL or PostgreSQL (required) | MIT | Poor: stale deps, requires external DB server |
| **audfprint** (dpwe/audfprint) | 2019-09 | Likely (deps: numpy, scipy, docopt, joblib) | Landmark/constellation (Dan Ellis original) | None built-in | pickle file (.pklz) | MIT | Moderate: right algorithm, file-based DB, but unmaintained 6+ years |
| **chromaprint/pyacoustid** (acoustid/chromaprint + beetbox/pyacoustid) | 2026-01 (chromaprint) / 2026-03 (pyacoustid) | Yes (actively maintained) | Chroma-based (NOT constellation map) | Partially robust (chroma is pitch-based, not time-delta-based) | AcoustID web service (remote) or local chromaprint lib | LGPL-2.1 (chromaprint) / MIT (pyacoustid) | Poor for SCUE: requires C library install, designed for global music ID not local DB matching, no time-offset matching |
| **Custom (recommended)** | N/A | Yes | Constellation map per design doc | Can implement any approach | JSON sidecar or SQLite | N/A | Best: tailored to SCUE, reuses librosa, no new deps |

**Detail:**

- **dejavu** (6.7k stars): The most well-known Python Shazam clone. Implements the full Wang 2003 algorithm. However, it has not been maintained since 2020. Its pinned dependencies (numpy 1.17, scipy 1.3, PyAudio 0.2.11) are incompatible with Python 3.11+. It requires a running MySQL or PostgreSQL instance for the fingerprint database, which is a non-starter for SCUE (local-only, no external DB servers). 133 open issues. Would require significant forking and modernization to use.

- **audfprint** (597 stars): Written by Dan Ellis (Columbia, the researcher behind the original Matlab landmark fingerprinting code that inspired Shazam). This is the most algorithmically sound option. It uses pickle files for its database (no external DB needed), pure Python with minimal dependencies (numpy, scipy, docopt, joblib). However, it has not been updated since 2019. The dependencies are not pinned to old versions, so it likely still works on Python 3.11+, but this is unverified. It has no tempo-change handling. The codebase is a CLI tool, not a library — using it programmatically would require importing internal modules or wrapping the CLI.

- **chromaprint/pyacoustid** (1.2k + 379 stars): Actively maintained (chromaprint updated Jan 2026, pyacoustid updated Mar 2026). However, it uses a fundamentally different approach: chroma-based fingerprinting (12-bin pitch class profiles over time), not constellation maps. It is designed for identifying recordings against the global AcoustID database, not for local collection matching with time-offset alignment. It cannot tell you "this audio matches track X starting at offset 45.2 seconds" — it only gives a recording-level match. This makes it unsuitable for the degraded-mode use case where SCUE needs to identify the playing track AND know where in the track the playback is. Additionally, chromaprint is a C++ library requiring compilation or binary distribution.

- **Custom implementation**: The design doc's algorithm is well-specified (Wang 2003 is a 6-page paper). The core is ~500-800 lines of Python: spectrogram peak picking, combinatorial hashing, and hash storage/lookup. SCUE already loads audio via librosa at SR=22050 with STFT parameters configured. The fingerprint generator would reuse the already-loaded audio signal, add a spectrogram + peak-picking step, and store hashes alongside the TrackAnalysis JSON. No new dependencies required beyond numpy/scipy (already in the stack).

**Confidence:** HIGH for dejavu/audfprint/chromaprint assessments (verified via GitHub API: commit dates, dependency files, repo metadata). MEDIUM for custom implementation effort estimate (based on algorithm complexity and existing codebase structure, not a prototype).

---

### Question 2: Cost of Adding Offline Fingerprint Generation

**Answer:** Low cost. Estimated additional time per track: 0.5-1.5 seconds. Storage per track: 50-200 KB (for a 5-minute track at ~20 hashes/second = ~6000 hashes, each 8-12 bytes). Implementation effort: 2-3 days for a developer familiar with the codebase.

**Detail:**

The analysis pipeline (`scue/layer1/analysis.py`) already:
1. Loads the full audio signal via librosa (SR=22050, mono) in step 2
2. Computes STFT-derived features (step 2, `extract_all`)
3. Stores results as JSON files keyed by SHA256 fingerprint

Adding constellation-map fingerprinting would insert a new step between steps 8 and 9 (after section scoring, before waveform computation). The implementation would:

1. Compute a spectrogram from the already-loaded `features.signal` (reuse the signal, compute a separate STFT optimized for peak-picking — likely at a lower sample rate like 8000-11025 Hz for efficiency)
2. Find spectral peaks (local maxima with uniform density filtering)
3. Generate combinatorial hashes (pairs of peaks within a target zone)
4. Store hashes as a sidecar field in TrackAnalysis or as a separate `.fp` file alongside the JSON

**Cost breakdown:**
- Spectrogram computation: ~0.2s (5-min track at 11025 Hz)
- Peak picking: ~0.1s
- Hash generation: ~0.2-0.5s (combinatorial, but sparse peaks keep it fast)
- Total added time: ~0.5-1.0s per track (current pipeline is 3-4s, so ~15-25% increase)
- Storage: ~6000 hashes x 12 bytes = ~72 KB per 5-minute track. Negligible vs the existing JSON (sections, beats, downbeats, waveform data)
- For 2000-track library: ~140 MB total fingerprint data. Acceptable.

**Implementation effort:**
- New module: `scue/layer1/constellation.py` (~300-500 lines: spectrogram, peak picker, hash generator, storage format)
- Modify `analysis.py`: Add step 9.5 (1-2 lines to call the generator, store result)
- Modify `models.py`: Add `constellation_hashes: list[int] | None = None` field to TrackAnalysis (or store separately)
- Tests: ~50-100 lines (determinism, hash count sanity, known-track matching)
- Total: 2-3 developer-days

The key advantage of doing this early: every track analyzed from now on accumulates fingerprints. When live matching is implemented later, the database is already populated.

**Confidence:** MEDIUM — estimates are based on algorithm analysis and codebase structure, not a working prototype. The 0.5-1.5s estimate could be higher if peak density tuning requires multiple passes.

---

### Question 3: Tempo-Invariant Hashing (Approach #3)

**Answer:** No known maintained open-source implementation exists. The approach is described in academic literature but not packaged as a library. It is moderately more complex than standard Shazam hashing — roughly 50-80% more implementation effort — because it requires 3-point (triplet) hash construction instead of 2-point (pair) construction, and ratio-based encoding instead of absolute delta encoding.

**Detail:**

The standard Shazam hash encodes: `(freq1, freq2, time_delta)` — a 32-bit value from a pair of peaks. Under tempo change, `time_delta` scales linearly, breaking the hash.

The tempo-invariant approach encodes: `(freq1, freq2, freq3, time_ratio_1_2, time_ratio_1_3)` — ratios of time deltas between three peaks. Under linear tempo change (pitch fader), all time deltas scale by the same factor, so ratios are preserved.

**Added complexity vs standard approach:**
- Hash generation: Instead of iterating pairs in a target zone, iterate triplets. Combinatorial explosion is managed by limiting the target zone size, but there are more combinations per anchor point.
- Hash size: 64-bit instead of 32-bit (to encode 3 frequencies + 2 ratios with sufficient precision). This is actually aligned with the 64-bit improvement noted in the design doc.
- Ratio quantization: Time ratios are continuous values that must be quantized into discrete bins. The bin width determines tolerance to small tempo variations vs. false match rate. This is a tuning parameter that does not exist in the standard approach.
- Matching: Same histogram approach works, but the hash space is larger (64-bit), so the database must be structured for efficient 64-bit lookup.
- Storage: Roughly 2x per hash (64-bit vs 32-bit), but hash count per track may be similar or slightly higher.

**Implementation effort:** ~4-5 developer-days (vs 2-3 for standard approach). The conceptual leap is small — it is the same constellation-map framework — but the triplet enumeration, ratio quantization, and 64-bit hash handling add implementation and tuning work.

**Critical insight from the design doc:** The design doc recommends approach #1 (normalize at query time using known pitch) but correctly notes this requires pitch data from the bridge, which is the exact data that is unavailable in the degraded mode where fingerprinting is the fallback. This makes approach #3 (tempo-invariant) the only approach that works in the worst case. However, approach #1 covers the more common partial-degradation scenarios (bridge running but metadata missing — pitch data IS available via UDP even in fallback mode).

**Recommendation:** Implement approach #1 first (simpler, covers most use cases). If fingerprint generation is added to offline analysis now, the stored hashes work with approach #1. Approach #3 can be added later as an alternative hash set stored alongside the standard hashes — the offline generation step would compute both.

**Confidence:** MEDIUM — based on algorithm analysis and literature review, not an implementation. No maintained open-source reference was found to validate feasibility estimates against.

---

### Question 4: Timeline — Where to Insert Fingerprint Generation

**Answer:** The natural insertion point is during Milestone 7 (Event Detection, Layer 1A Tier 2), not earlier. Milestone 7 is the next time the offline analysis pipeline is being modified, so adding fingerprint generation there avoids disrupting the current M3-M6 trajectory (which is focused on Layers 2-4 and does not touch Layer 1A). However, if fingerprint accumulation is a priority, a lightweight "Milestone 1B" could be inserted between M3 and M4 with minimal risk.

**Detail:**

Current milestone trajectory:
- **M3** (next): Cue Stream — Layer 2, does not touch Layer 1A analysis pipeline
- **M4**: Basic Effect Engine — Layer 3, does not touch Layer 1A
- **M5**: DMX Output — Layer 4, does not touch Layer 1A
- **M6**: End-to-End Demo — integration, does not touch Layer 1A
- **M7**: Event Detection — Layer 1A Tier 2. **This is the next milestone that modifies the offline analysis pipeline.** Adding fingerprint generation here is zero-disruption.
- **M11**: Polish & Tier 3 — where fingerprinting was originally planned

**Option A: Add at M7 (recommended).** When the analysis pipeline is already being extended for event detection, add constellation-map generation as an additional step. The pipeline is already being modified, tests are already being updated, and the new module slots in cleanly. Every track analyzed from M7 onward accumulates fingerprints. Live matching is still deferred (M11 or later), but the database grows passively.

**Option B: Standalone "M1B" mini-milestone between M3 and M4.** If the goal is to start accumulating fingerprints immediately (e.g., because a large library re-scan is planned soon), this could be a 2-3 day effort slotted between milestones. Risk: it delays M3 by 2-3 days. Benefit: all 2000+ tracks get fingerprinted during the next batch analysis run.

**Option C: Keep at M11.** No disruption, but no fingerprint accumulation until late in the project. If a re-scan is needed at M11 just to generate fingerprints for existing tracks, it costs the same 2-3 days plus the re-scan time.

**Recommendation:** Option A (M7). The 2-3 day implementation fits naturally into a milestone that is already modifying the analysis pipeline. The fingerprint database grows from M7 onward, which gives 4 milestones of accumulation before live matching would be implemented.

If Brach plans a full library re-scan before M7 (e.g., after adding event detection features), then Option B is worth considering to ensure that re-scan also generates fingerprints — avoiding a second full-library pass later.

**Confidence:** HIGH — based on direct reading of MILESTONES.md and the analysis pipeline code structure.

## Recommended Next Steps

1. **No immediate action required.** The current M3 trajectory should not be disrupted for fingerprinting.
2. **When M7 planning begins:** Include "constellation-map fingerprint generation" as a task in the M7 spec. Estimated effort: 2-3 days, no new dependencies. The implementation is a new module (`scue/layer1/constellation.py`) plus a one-line addition to the analysis pipeline.
3. **Decision needed before M7:** Standard hashing only (approach #1), or also generate tempo-invariant hashes (approach #3)? If both, add ~2 extra days. Recommend starting with standard only and adding tempo-invariant as a separate pass if degraded-mode matching becomes a priority.
4. **Skip dejavu and audfprint.** Neither is maintained or architecturally suitable. A custom implementation using the existing librosa/numpy/scipy stack is lower-risk and better-fit.
5. **Skip chromaprint/pyacoustid.** Wrong algorithm for SCUE's needs (no time-offset matching, external C dependency, designed for global DB not local collection).

## Skill File Candidates

- `skills/audio-fingerprinting.md` — should be created when implementation begins (M7). Should contain: constellation-map algorithm summary, hash format specification, peak-picking parameters, target zone geometry, storage format, and the tempo-invariant variant description. Not needed yet since no code exists.
