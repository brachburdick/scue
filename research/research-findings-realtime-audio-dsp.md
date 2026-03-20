# Research Findings: Real-Time Audio DSP for Deck Weight Estimation

## Questions Addressed
1. What Python libraries support real-time audio capture on macOS, and what latencies/buffer sizes are practical?
2. How can cross-correlation and template matching be used to match a live audio stream against known reference waveforms?
3. Can stereo field analysis and source separation distinguish two DJ tracks mixed to stereo?
4. Is it feasible to estimate deck mixing ratios in real-time using known spectral features of loaded tracks?

## Findings

### Question 1: Real-Time Audio Capture on macOS with Python

**Answer:** `sounddevice` (PortAudio bindings) is the best general-purpose choice for SCUE. It records directly to NumPy arrays, has asyncio support via coroutine-based streams, and provides CoreAudio-specific settings on macOS. Round-trip latency of 5-12ms is achievable with 256-sample buffers at 44.1kHz. Python can handle real-time audio at 44.1/48kHz without drops, provided DSP runs in C-backed NumPy/SciPy operations (not pure Python loops).

**Detail:**

**Library comparison:**

| Library | NumPy native | asyncio support | macOS CoreAudio | Maintenance | SCUE fit |
|---|---|---|---|---|---|
| **sounddevice** | Yes (records to arrays) | Yes (asyncio coroutine example in docs) | Yes (CoreAudioSettings class) | Active | Best |
| **pyaudio** | No (records to bytes) | No | Yes (via PortAudio) | Sporadic | Acceptable |
| **python-rtmixer** | Yes | No (C callbacks) | Yes | Active | Overkill (designed for ultra-low-latency) |
| **SoundCard** | Yes | No | Yes (native CoreAudio) | Active | Alternative |
| **audiolazy** | Custom stream class | No | Limited | Stale | Poor |

**Buffer sizes and latency at 44.1kHz:**

| Buffer (samples) | Latency (ms) | CPU overhead | Reliability | Use case |
|---|---|---|---|---|
| 128 | 2.9 | Very high | Risk of dropouts | Not recommended for Python |
| 256 | 5.8 | High | Workable on macOS | Minimum for real-time DSP |
| 512 | 11.6 | Moderate | Reliable | Good default for SCUE |
| 1024 | 23.2 | Low | Very reliable | Conservative / analysis-focused |
| 2048 | 46.4 | Very low | Rock solid | Sufficient for beat-level tracking |

**Key considerations:**
- sounddevice callbacks run in a separate C thread via PortAudio, so they are not affected by the GIL. However, the callback itself must be fast (no allocations, no Python-heavy work). The pattern is: callback fills a ring buffer, main thread (or asyncio loop) reads and processes.
- `python-rtmixer` implements audio callbacks entirely in C (avoiding GIL and GC pauses) for the most demanding use cases, but adds complexity.
- For SCUE's use case (analysis at beat/bar rate, not sample-accurate instrument processing), 512 or 1024 sample buffers are more than adequate. The DSP processing window will likely be much larger than the capture buffer anyway.
- macOS CoreAudio is one of the best-behaved audio APIs; latency of ~6ms with 256-sample buffers is typical and reliable.

**Sources:**
- [python-sounddevice docs](https://python-sounddevice.readthedocs.io/en/0.4.1/) — official documentation, HIGH relevance
- [python-rtmixer](https://github.com/spatialaudio/python-rtmixer) — C-callback alternative, MEDIUM relevance
- [Real-time Audio Processing (DeepWiki)](https://deepwiki.com/spatialaudio/python-sounddevice/4.3-real-time-audio-processing) — architecture overview, HIGH relevance
- [Audio APIs: CoreAudio (Bastibe)](https://bastibe.de/2017-06-17-audio-apis-coreaudio.html) — macOS-specific behavior, HIGH relevance
- [Real Time Signal Processing in Python (Bastibe)](https://bastibe.de/2012-11-02-real-time-signal-processing-in-python.html) — latency benchmarks, MEDIUM relevance
- [sounddevice latency issue #524](https://github.com/spatialaudio/python-sounddevice/issues/524) — practical latency discussion, MEDIUM relevance

**Confidence:** HIGH for sounddevice recommendation and buffer size guidance. Multiple corroborating sources, well-documented library. MEDIUM for exact latency numbers (hardware-dependent, not tested on SCUE's target hardware).

---

### Question 2: Cross-Correlation and Template Matching for Audio

**Answer:** Direct cross-correlation of raw waveforms is computationally expensive but feasible for short windows using FFT-based methods (`scipy.signal.correlate` with `method='fft'`). For SCUE's use case, correlating spectral features (chromagrams, MFCCs) rather than raw audio is strongly preferred: it is cheaper, more robust to EQ/gain changes, and provides sufficient temporal resolution for beat-level tracking.

**Detail:**

**Raw waveform cross-correlation:**
- Cost: O(N log N) via FFT, where N is the longer signal length. For a 1-second window at 44.1kHz, N=44100. FFT of this size takes ~0.1ms on modern hardware. Feasible in real-time.
- Problem: Raw correlation is sensitive to gain changes, EQ adjustments, and phase shifts from the DJ mixer. A DJ turning the bass knob changes the waveform significantly without changing "what track is playing."
- Normalized cross-correlation helps with gain but not with EQ.

**Spectral feature cross-correlation (recommended for SCUE):**
- Chromagram: 12 bins per frame, one frame per ~23ms (512-sample hop at 22050Hz). Cross-correlating a 4-second window of chromagram = correlating 12x170 feature matrices. Very cheap.
- Chromagrams are robust to EQ changes in ways raw audio is not, because they represent pitch class energy distribution. A bass cut changes the amplitude of low-frequency components but the chroma profile (which sums across octaves) is more stable.
- MFCC: 13-20 coefficients per frame. Good for timbral matching. More sensitive to EQ than chroma but captures more detail.
- Retrieval accuracy with chromagram features reaches >96.7% even at 0dB SNR (i.e., when the signal is as loud as the noise).

**Fingerprint constellation map approach (Shazam-style):**
- Designed for identifying which track is playing, not for continuous position tracking.
- Uses spectrogram peaks as landmarks, hashes pairs of peaks by frequency delta and time delta.
- Very fast lookup (hash table), robust to noise and compression.
- However: gives you "this is track X" and a rough time offset, not a continuous real-time position estimate.
- Best used as a coarse identification step, then refined with cross-correlation.
- A combined approach has been proposed in the literature: fingerprint matching for coarse frame-accurate sync, then generalized cross-correlation with phase transform (GCC-PHAT) for fine alignment.

**Recommended approach for SCUE:**
1. Use existing constellation-map fingerprinting (per prior research findings) for track identification as a fallback/verification.
2. For continuous position tracking and deck weight estimation, use short-time chromagram cross-correlation against pre-computed chromagram features from the analysis pipeline.
3. This aligns with SCUE's architecture: pre-analyzed spectral features are already available per track.

**Sources:**
- [scipy.signal.correlate docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.correlate.html) — FFT-based correlation, HIGH relevance
- [Find audio within audio (DEV Community)](https://dev.to/hiisi13/find-an-audio-within-another-audio-in-10-lines-of-python-1866) — practical example, MEDIUM relevance
- [Audio Identification (AudioLabs Erlangen)](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C7/C7S1_AudioIdentification.html) — constellation map theory, HIGH relevance
- [Chromagram retrieval method (IEEE)](https://ieeexplore.ieee.org/document/5684543/) — chromagram vs MFCC for matching, HIGH relevance
- [Fast second screen sync (IEEE)](https://ieeexplore.ieee.org/document/6336458/) — combined fingerprint + cross-correlation, HIGH relevance
- [librosa feature extraction docs](https://librosa.org/doc/0.11.0/feature.html) — feature computation reference, HIGH relevance

**Confidence:** HIGH for spectral feature matching recommendation. Well-established MIR technique with strong literature support. MEDIUM for specific computational cost claims (not benchmarked in SCUE's pipeline).

---

### Question 3: Stereo Field Analysis for Source Separation

**Answer:** Mid/side processing can reveal some information about source separation when two tracks are mixed, but it is unreliable as a primary method because DJ mixers sum both decks to both L and R channels (both sources appear in the mid channel). Informed source separation (ISS), where the reference signals are known, is far more promising and directly applicable to SCUE since we know what tracks are loaded.

**Detail:**

**What happens when a DJ mixer blends two tracks:**
- Most DJ mixers sum Deck A and Deck B to a stereo master bus. Both tracks appear in both L and R channels. The mix is not "Deck A left, Deck B right."
- The mixer's crossfader and channel faders control the amplitude ratio, but both signals occupy the full stereo field.
- Therefore, mid/side decomposition does NOT cleanly separate the two decks. Both tracks contribute to both mid and side channels.
- Exception: if the two tracks have different stereo characteristics (e.g., one is mono, one is wide stereo), mid/side may reveal some differential. But this is unreliable and track-dependent.

**Mid/side processing — what it can and cannot do:**
- Mid = (L+R)/2, Side = (L-R)/2.
- Mid contains everything common to both channels. Side contains the stereo difference.
- For DJ mixing: both tracks appear in mid. Tracks with more stereo content will have more side energy, but this doesn't separate them.
- Mid/side is useful for mastering and EQ, not for DJ source separation.

**Informed Source Separation (ISS) — the promising approach:**
- When you have the reference signals (the original tracks), separation becomes dramatically easier.
- The problem reduces from blind source separation (very hard) to informed source separation (tractable).
- Approach: extract spectral envelopes from original tracks, use them as templates to decompose the live mix signal via time-frequency masking.
- ISS literature shows this works with STFT windows of 2048 samples (~46ms at 44.1kHz), which is well within real-time constraints.
- The key insight: you don't need to perfectly separate the tracks. You just need to estimate the mixing ratio (how much of each track is present), which is a much simpler problem.

**NMF (Non-Negative Matrix Factorization):**
- NMF decomposes a spectrogram V into W (spectral templates) x H (activation weights).
- In the supervised/informed case: W is fixed (known spectral templates from pre-analyzed tracks), only H needs to be estimated.
- With fixed W, this is a simple non-negative least squares problem, much cheaper than full NMF.
- Standard NMF is iterative and too expensive for real-time on full spectrograms. But with fixed W templates, a single NNLS solve per frame is feasible.
- scikit-learn's `NMF` and scipy's `nnls` are available for this.

**Simpler approaches — energy ratio estimation:**
- If you know the expected spectral energy profile of each track at the current playback position, you can estimate mixing ratios by comparing the live spectrum to a weighted combination of the two known spectra.
- This is a least-squares problem: minimize ||S_live - (alpha * S_A + beta * S_B)||^2, where S_A and S_B are the known spectral profiles and alpha/beta are the mixing weights.
- This can be solved per-frame in microseconds with numpy.linalg.lstsq.
- EQ adjustments on the mixer will distort this estimate, but band-specific estimation (bass/mid/high separately) can partially account for this.

**Sources:**
- [Informed Source Separation overview (HAL)](https://hal.science/hal-00958661/document) — comprehensive ISS survey, HIGH relevance
- [Stereo signal separation by mid-side decomposition (DAFx)](https://www.dafx.de/paper-archive/2015/DAFx-15_submission_9.pdf) — mid/side for source separation, HIGH relevance
- [Score-informed source separation (Ewert)](https://interactiveaudiolab.github.io/assets/papers/score_informed_source_separation.pdf) — using known reference for separation, HIGH relevance
- [NMF for audio source separation (Medium)](https://medium.com/@zahrahafida.benslimane/audio-source-separation-using-non-negative-matrix-factorization-nmf-a8b204490c7d) — NMF overview, MEDIUM relevance
- [Informed ISS from compressed mixtures (HAL)](https://hal.science/hal-00725428/document) — practical ISS implementation, HIGH relevance
- [Mid/Side processing explained (LANDR)](https://blog.landr.com/what-is-mid-side/) — M/S fundamentals, MEDIUM relevance

**Confidence:** HIGH that mid/side alone is insufficient for DJ source separation. HIGH that informed source separation is the right framework. MEDIUM for real-time feasibility of full ISS (depends on implementation complexity). HIGH that simplified least-squares energy ratio estimation is feasible in real-time.

---

### Question 4: Practical DSP for Deck Weight Estimation

**Answer:** Yes, estimating the mixing ratio (deck A weight vs. deck B weight) is feasible in real-time by comparing the live audio spectrum to the known spectra of each loaded track. The recommended approach is per-band least-squares fitting at 4-10 Hz update rate, using pre-computed spectral energy profiles from the analysis pipeline. EQ adjustments can be partially accounted for by estimating per-band (bass/mid/high) weights independently.

**Detail:**

**Core algorithm — spectral energy least squares:**

Given:
- `S_live[f]` = live audio power spectrum (e.g., 512 frequency bins from a 1024-point FFT)
- `S_A[f]` = expected power spectrum of Track A at current playback position (from pre-analysis)
- `S_B[f]` = expected power spectrum of Track B at current playback position

Solve: `S_live ≈ alpha * S_A + beta * S_B` via least squares.

- `alpha` and `beta` are the estimated deck weights (mixing ratio).
- Constrained: alpha >= 0, beta >= 0 (use `scipy.optimize.nnls` or clamp negative values).
- Cost: one `numpy.linalg.lstsq` call with a 512x2 matrix. Takes ~10 microseconds. Trivially real-time.

**Which spectral features are most discriminative:**

| Feature | Dimensionality | EQ sensitivity | Discriminative power | Computation cost |
|---|---|---|---|---|
| Power spectrum (full) | 512-2048 bins | HIGH (directly affected) | HIGH (most detail) | Low |
| Mel-frequency bands | 40-128 bands | HIGH | HIGH | Low |
| Chromagram | 12 bins | LOW (sums across octaves) | MEDIUM (pitch only) | Moderate |
| Spectral centroid | 1 value | MEDIUM | LOW (too coarse) | Very low |
| MFCC | 13-20 values | MEDIUM | MEDIUM-HIGH | Moderate |
| Band energy (bass/mid/high) | 3 values | HIGH (but interpretable) | MEDIUM | Very low |

**Recommended feature set for SCUE:**
- Primary: Mel-frequency bands (40-80 bands). Good balance of resolution and robustness.
- Secondary: 3-band energy ratio (bass/mid/high, roughly <250Hz / 250-4kHz / >4kHz). Cheap, interpretable, and directly maps to DJ mixer EQ bands.
- The 3-band approach is particularly interesting because DJ mixers expose exactly these three bands (low/mid/high EQ knobs), so the mapping to "what the DJ is doing" is direct.

**Handling EQ adjustments:**

- EQ changes on the DJ mixer alter the spectral profile of each deck before summing.
- If you estimate per-band weights independently, you can detect EQ cuts:
  - `alpha_bass, beta_bass` from low-frequency bins
  - `alpha_mid, beta_mid` from mid-frequency bins
  - `alpha_high, beta_high` from high-frequency bins
- If `alpha_bass` drops to near zero while `alpha_mid` and `alpha_high` remain, the DJ has cut the bass on Deck A.
- This actually gives you MORE information than a single mixing ratio: you can infer EQ positions.

**Update rate:**

| Rate | Window size (at 44.1kHz) | Latency | Use case |
|---|---|---|---|
| Per-sample | N/A | <1ms | Unnecessary and impossible |
| 100 Hz (every 10ms) | 441 samples | 10ms | Excessive for SCUE |
| 10 Hz (every 100ms) | 4410 samples | 100ms | Good for smooth weight tracking |
| Per-beat (~2 Hz at 128 BPM) | ~20k samples | 469ms | Natural for beat-synced cues |
| Per-bar (~0.5 Hz) | ~80k samples | 1.9s | Sufficient for transition detection |

**Recommended for SCUE:** 4-10 Hz update rate (100-250ms windows). This provides smooth weight tracking, aligns well with musical time, and is trivially achievable computationally. The weight values can be smoothed with an exponential moving average to avoid jitter.

**End-to-end pipeline for SCUE:**

```
Audio capture (sounddevice, 512-sample buffer, 44.1kHz)
  → Accumulate to analysis window (4096-8192 samples, ~100-200ms)
  → FFT → power spectrum → mel-band energy
  → Look up expected spectra for Track A and Track B at current playback positions
  → Least-squares solve for [alpha, beta]
  → Optional: per-band solve for [alpha_bass, alpha_mid, alpha_high, beta_bass, beta_mid, beta_high]
  → Smooth with EMA (alpha=0.3)
  → Emit DeckWeight event to Layer 2 cue stream
```

Total computational cost per update: ~0.5ms (FFT + feature extraction + least squares). Leaves >99% of CPU time free.

**Important caveats:**
- This assumes playback position tracking is accurate (from beat-link bridge). Position drift will cause spectral mismatch.
- Two tracks with very similar spectral profiles (e.g., same genre, same energy) will be harder to distinguish. The least-squares solution becomes ill-conditioned.
- Effects (reverb, delay, filters) applied on the mixer will distort the estimate. These are harder to model.
- The approach works best during transitions (which is when you most need it) because the tracks are typically dissimilar enough for the least-squares to be well-conditioned.

**Sources:**
- [Informed Audio Source Separation (HAL)](https://hal.science/hal-00725428/document) — theoretical framework, HIGH relevance
- [Fully Constrained Least Squares Spectral Mixture Analysis (UMBC)](https://www2.umbc.edu/rssipl/pdf/TGRS/01/tgrs.3_01.pdf) — constrained least-squares for mixture decomposition (remote sensing, but same math), HIGH relevance
- [Real-Time Adaptive Audio Mixing System (Liu)](https://liu.diva-portal.org/smash/get/diva2:1058954/FULLTEXT01.pdf) — adaptive mixing ratio estimation, MEDIUM relevance
- [Spectral audio signal processing (CCRMA Stanford)](https://ccrma.stanford.edu/~jos/sasp/) — DSP fundamentals reference, MEDIUM relevance
- [Robust audio matching using spectral flatness (ResearchGate)](https://www.researchgate.net/publication/3927293_Robust_matching_of_audio_signals_using_spectral_flatness_features) — spectral feature robustness, MEDIUM relevance

**Confidence:** HIGH that least-squares spectral decomposition is computationally feasible in real-time. HIGH that mel-band and 3-band energy features are appropriate. MEDIUM for accuracy of mixing ratio estimates in practice (untested, depends on track similarity, EQ, effects). LOW for handling of mixer effects (reverb, delay) — this remains an open problem.

---

## Recommended Next Steps

1. **Prototype audio capture**: Build a minimal `sounddevice` InputStream that captures to a ring buffer and computes mel-band energy per 100ms window. Verify latency and dropout behavior on the target Mac hardware.
2. **Prototype deck weight estimation**: Using two known WAV files mixed at known ratios, verify that the least-squares spectral decomposition recovers the correct mixing weights. Test with and without EQ changes.
3. **Integrate with analysis pipeline**: Ensure that the pre-computed spectral features (mel spectrogram) from Layer 1 analysis are stored at sufficient temporal resolution for the lookup step (one frame per ~23ms hop is typical from librosa).
4. **Define the DeckWeight event schema**: Add a new event type to Layer 2 contracts — `DeckWeight { deck_a_weight: float, deck_b_weight: float, per_band: {bass: [a, b], mid: [a, b], high: [a, b]}, timestamp: float }`.
5. **Evaluate constellation-map fingerprinting** for fallback track identification (when beat-link bridge data is unavailable), per the prior research findings document.

## Skill File Candidates

- **`skills/realtime-audio-capture.md`**: sounddevice setup on macOS, buffer size selection, asyncio integration pattern, CoreAudio settings. Developers will need this for any audio capture work.
- **`skills/spectral-matching.md`**: Least-squares spectral decomposition for mixing ratio estimation, per-band EQ-aware estimation, feature selection (mel bands vs. chroma vs. MFCC). This is the core algorithm for deck weight estimation.
- **`skills/informed-source-separation.md`**: Overview of ISS techniques applicable to SCUE (NNLS with known spectral templates, mid/side limitations). Useful if the approach needs to be extended beyond simple weight estimation.
