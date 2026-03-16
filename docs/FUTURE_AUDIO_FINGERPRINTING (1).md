# Future Enhancement: Audio Fingerprint-Based Track Identification

## Summary

Shazam-style audio fingerprinting (spectrogram peak constellation maps with combinatorial hashing) could serve as a fallback track identification method when beat-link metadata is unavailable. This would allow SCUE to identify which pre-analyzed track is playing by capturing a few seconds of live audio and matching it against a fingerprint database, independent of rekordbox metadata.

## Source

Wang, A. L-C. (2003). "An Industrial-Strength Audio Search Algorithm." Shazam Entertainment, Ltd. Presented at ISMIR 2003.

## How It Works

1. **Constellation maps:** A spectrogram is reduced to a sparse set of peak coordinates (time, frequency). Peaks are selected by local energy maxima with uniform density coverage. Amplitude is discarded — only coordinates are kept.
2. **Combinatorial hashing:** Pairs of peaks are formed by associating anchor points with points in a target zone. Each pair yields a 32-bit hash encoding two frequency values and the time delta between the points. Each hash is associated with its absolute time offset in the file.
3. **Matching:** Hashes from an unknown sample are matched against the database. For each candidate track, matching hash pairs produce (sample_time, database_time) coordinates. A true match produces a cluster of points on a diagonal line in this scatterplot. Detection reduces to finding a peak in the histogram of time offsets (database_time - sample_time). A statistically significant cluster indicates a match.

The algorithm achieves correct identification with as few as 1-2% of hash tokens surviving from the original, making it robust against heavy noise, dropout, and codec compression.

## Relevance to SCUE

**Where it fits:** Alternative track matching strategy in Layer 1B, alongside the primary beat-link metadata matcher.

**When it adds value:** Beat-link is in degraded mode (no metadata), DJ is playing from a USB not prepared in rekordbox, guest DJ at a b2b set, or any scenario where track metadata is unavailable but audio is capturable.

**Where it does NOT help:** Section segmentation, event detection, beat tracking, cue generation, or any analysis task. Fingerprinting identifies *what's playing*, not *what's happening in the music*.

## Implementation Approach

**Offline (Layer 1A):** During track analysis, generate a constellation-map fingerprint and store it alongside the TrackAnalysis JSON file. Storage is small — fingerprints are orders of magnitude smaller than the audio.

**Live matching (Layer 1B):** If beat-link metadata is unavailable, capture a few seconds of audio from the deck and match against the fingerprint database.

### Handling Tempo Changes

The Shazam algorithm as published does not handle tempo-adjusted playback. Hashes encode absolute time deltas between peak pairs, which change when the track is sped up or slowed down. DJ filter effects (EQ, high-pass, low-pass) are well-tolerated — peaks in unaffected frequency bands survive with the same coordinates.

Three approaches to handle tempo, in order of recommendation for SCUE:

1. **Normalize at query time (recommended).** SCUE almost always knows the pitch adjustment from the bridge (even in basic UDP mode, pitch data is available). Time-stretch the captured audio back to the original tempo before generating the query fingerprint. Simple resample, one fingerprint stored per track, and it works whenever pitch data is available.

2. **Pre-compute at multiple tempos.** Generate fingerprints at the original BPM ±8% in 0.5% increments (~33 versions per track). Query against the version matching the current pitch. Brute-force but simple. Storage multiplies by ~33x per track but fingerprints are small.

3. **Tempo-invariant hash construction.** Encode ratios of time deltas between 3+ points instead of absolute deltas. Ratios are preserved under linear time scaling. More complex to implement but works even without knowing the pitch adjustment. Aligns with the 64-bit hash improvement noted below.

### 64-Bit Hash Improvement (Post-2003)

The original paper uses 32-bit hashes (2 frequencies + 1 time delta) due to 2003-era constraints. With 64-bit integers, you can use 3 anchor points per target zone point, encoding a hash as (f1, f2, f3, f4, Δt1, Δt2, Δt3). This dramatically reduces false matches and search time. The approach also enables high parallelism: the fingerprint database can be sharded across D partitions, searched in parallel, with results merged — achieving D-times speedup linearly.

## Priority

**Low. Deferred to post-Milestone 11.**

Beat-link provides reliable track identification through rekordbox metadata for the vast majority of use cases. The fingerprint approach is a robustness enhancement for edge cases (degraded mode, unknown USB, guest DJ). The core pipeline (analysis → bridge → cursor → cues → effects → output) must work first.

When implemented, it is a self-contained addition: a fingerprint generator added to the Layer 1A analysis pipeline, a fingerprint matcher added to Layer 1B as a fallback identification strategy, and a small fingerprint store alongside the existing track analysis JSON files. No changes to Layers 2–4 or the frontend are required.

## Architectural Note

The track fingerprint used for identification (constellation-map hash) is a different concept from the track fingerprint used as the database key (SHA256 audio hash). The SHA256 hash is a content-addressable identifier — it tells you whether two files are byte-identical. The constellation-map fingerprint is a perceptual identifier — it tells you whether two audio signals sound like the same recording, even if they differ in format, encoding, or minor processing. Both have a role: SHA256 for deduplication and file management, constellation-map for live audio matching.
