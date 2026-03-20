# Research Findings: Pioneer Hardware Topology, Audio Capture & Deck Identification

## Questions Addressed
1. Can a legacy CDJ be connected to the XDJ-AZ via Pro DJ Link? Will beat-link work with it?
2. How does the XDJ-AZ appear on the Pro DJ Link network? What about external player connectivity?
3. How do professional DJ lighting/VJ tools handle real-time audio input?
4. Can you identify which deck is contributing to a stereo master mix using DSP?

---

## Findings

### Question 1: Legacy CDJ Connected to XDJ-AZ via Pro DJ Link

**Answer:** Yes, a legacy CDJ can connect to the XDJ-AZ via Pro DJ Link, but with important caveats about audio routing and physical connectivity.

**Confidence: HIGH** (based on official AlphaTheta support documentation)

**Detail:**

#### Physical Connectivity
- The XDJ-AZ has **one LAN (LINK EXPORT) port** on the rear panel (CAT5e).
- A single legacy CDJ (e.g., CDJ-2000NXS2) can be connected **directly** to this port with a single Ethernet cable.
- For **more than one external player**, an external Ethernet switch/hub is required (the XDJ-AZ no longer ships with a link hub).

#### Pro DJ Link Behavior
- The CDJ-2000NXS2 would appear as a **separate, standard Pro DJ Link device** on the network.
- beat-link's MetadataFinder/CrateDigger should work **normally** with the legacy CDJ, since it uses the standard DBServer protocol (not DLP).
- USB media sharing works across the link — tracks on a USB plugged into either the XDJ-AZ or the CDJ can be browsed from either device.

#### Audio Routing (Critical Limitation)
- The LAN cable carries **only data** (track metadata, sync, link export). It does **NOT** carry audio.
- To route the legacy CDJ's audio through the XDJ-AZ's mixer, a **separate audio cable** is required.
- The XDJ-AZ has **PHONE (1/4" unbalanced) inputs** for external sources, not RCA. Since CDJs output via RCA, an **RCA-to-1/4" adapter/cable** is needed.
- The external CDJ audio would come in on one of the XDJ-AZ's external input channels, not as a native deck.

#### Maximum Devices on Pro DJ Link
- Standard limit: **4 players** (device numbers 1-4) when mixing legacy and modern hardware.
- CDJ-3000/CDJ-3000X only: up to **6 players**.
- The XDJ-AZ itself uses higher device numbers (like the OPUS-QUAD pattern: 9-12 for decks 1-4), so a legacy CDJ using device number 1-4 should **not conflict**.

**Sources:**
- [AlphaTheta: Can I connect CDJs to XDJ-AZ via PRO DJ LINK?](https://support.pioneerdj.com/hc/en-us/articles/38063890981145-Can-I-connect-CDJs-and-a-DJM-to-the-XDJ-AZ-via-PRO-DJ-LINK)
- [AlphaTheta: Do I also need to connect an audio cable?](https://support.pioneerdj.com/hc/en-us/articles/4410630166297-I-connected-this-unit-and-a-CDJ-XDJ-with-a-LAN-cable-because-I-wish-to-use-the-PRO-DJ-LINK-function-Do-I-also-need-to-connect-an-audio-cable)
- [Pro DJ Link Setup (DJ TechTools)](https://djtechtools.com/2018/07/31/pro-dj-link-how-to-set-up-pioneer-dj-setups-properly/)
- [Pro DJ Link: The Ultimate Guide (DeeJay Plaza)](https://www.deejayplaza.com/en/articles/pro-dj-link)

---

### Question 2: Pro DJ Link Network Topology with XDJ-AZ

**Answer:** The XDJ-AZ likely appears as multiple virtual devices using high device numbers (9-12 pattern), similar to the OPUS-QUAD. It has one LAN port for external player connectivity.

**Confidence: MEDIUM** (XDJ-AZ-specific device numbers inferred from OPUS-QUAD analysis; confirmed that it uses DLP ID namespace)

**Detail:**

#### How All-in-One Units Appear on the Network
- The **OPUS-QUAD** (closely related architecture) appears on the network with device numbers **9=deck1, 10=deck2, 11=deck3, 12=deck4**. These are distinct from the standard 1-4 range used by standalone CDJs.
- The XDJ-AZ is expected to follow the same pattern, broadcasting keep-alive UDP packets on port 50000 with device type identifiers.
- The all-in-one units do **not** appear as separate "CDJ + mixer" devices — they appear as a single unit with multiple virtual player slots.

#### External Player Connectivity
- The XDJ-AZ has **one LAN (LINK EXPORT) port**.
- A legacy CDJ-2000NXS2 connected to this port would claim a device number in the **1-4 range** (configurable in Utility menu).
- There is no conflict because the XDJ-AZ uses the 9-12 range.
- For 2+ external players, an external Ethernet switch is required.

#### beat-link Implications
- beat-link would see the legacy CDJ as a standard device and use MetadataFinder/CrateDigger normally.
- beat-link would see the XDJ-AZ's decks as high-numbered devices requiring the OpusProvider/VirtualRekordbox approach (metadata archives, no DBServer).
- The XDJ-AZ **always uses Device Library Plus IDs**, so `CdjStatus.getRekordboxId()` returns DLP IDs, not standard rekordbox IDs.

**Sources:**
- [OPUS-QUAD Pro DJ Link Analysis (GitHub)](https://github.com/kyleawayan/opus-quad-pro-dj-link-analysis)
- [Beat Link Trigger: Working with the Opus Quad](https://blt-guide.deepsymmetry.org/beat-link-trigger/OpusQuad.html)
- [Digital DJ Tips: XDJ-AZ Questions Answered](https://www.digitaldjtips.com/xdj-az-your-questions-answered/)
- [Beat-Link GitHub](https://github.com/Deep-Symmetry/beat-link)

---

### Question 3: Real-Time Audio Capture for DJ Software

**Answer:** Professional DJ lighting software uses a mix of approaches: Pro DJ Link metadata (no audio needed), BPM detection from audio input, or direct line-in capture. For SCUE, a USB audio interface capturing the master out is the most flexible approach.

**Confidence: HIGH**

**Detail:**

#### How Existing Products Handle It

| Product | Audio Approach | Notes |
|---------|---------------|-------|
| **rekordbox Lighting / ShowKontrol** | No audio capture. Uses Pro DJ Link metadata (BPM, beats, phrases) from CDJs. | Requires CDJ-3000 + RB-DMX1. Phrase data sent over network. |
| **SoundSwitch** | BPM Detection from any audio source (mic, line-in). Also supports Ableton Link & MIDI Clock sync. | Does not use Pro DJ Link directly. Works with Serato, Engine DJ, etc. |
| **Resolume Arena** | Line-in audio via computer input or audio interface. Uses FFT for audio-reactive parameters. | Supports external FFT (line input), clip FFT, composition FFT. No capture card audio support. |

#### Audio Interface Setup for Master Out Capture

**Signal path:** DJ mixer master out -> audio interface line input -> USB -> computer

**Connection options (best to worst):**
1. **XLR (balanced)** from MASTER OUT1 -> XLR input on audio interface. Best noise rejection, longest cable runs.
2. **1/4" TRS (balanced)** from BOOTH OUT -> TRS input on audio interface. Same quality as XLR, useful if master outs are taken by PA.
3. **RCA (unbalanced)** from MASTER OUT2 -> RCA-to-1/4" adapter -> audio interface. Adequate for short runs.

**The XDJ-AZ specifically has:**
- MASTER OUT1: XLR (balanced)
- MASTER OUT2: RCA (unbalanced)
- BOOTH OUT: 1/4" TRS (balanced)

**Recommended interfaces for this use case:**
- Focusrite Scarlett 2i2 or similar 2-input USB interface (stereo capture)
- Audient EVO 4/8
- MOTU M2
- Any 2+ channel USB-C audio interface with line-level inputs

#### Latency on macOS

| Buffer Size (samples) | Sample Rate | Approx. Round-Trip Latency |
|----------------------|-------------|---------------------------|
| 32 | 44.1 kHz | ~3-4 ms |
| 64 | 48 kHz | ~5-8 ms |
| 128 | 44.1 kHz | ~8-10 ms |
| 256 | 44.1 kHz | ~15-18 ms |

- macOS uses **Core Audio** (not ASIO). Generally 1-3ms more latency than equivalent Windows ASIO.
- Apple Silicon (M1/M2/M3) performs well; typical round-trip at 64 samples / 48kHz is ~7-8ms with a Focusrite Scarlett.
- **For SCUE's use case (analysis, not monitoring), input-only latency is what matters** — roughly half the round-trip figure, so **3-5ms at practical buffer sizes**.
- For real-time DSP (onset detection, beat tracking), **44.1 kHz or 48 kHz** is sufficient. 96 kHz offers no meaningful benefit for rhythm/spectral analysis and doubles CPU load.

**Sources:**
- [SoundSwitch Official](https://www.soundswitch.com/)
- [SoundSwitch: Introduction](https://support.soundswitch.com/en/support/solutions/articles/69000847099-introduction-to-soundswitch)
- [Resolume: Audio Reactive Training](https://www.resolume.com/training/2/11/67)
- [Pioneer DJ: Pro DJ Link Lighting Setup](https://support.pioneerdj.com/hc/en-us/articles/9407779713177-How-to-set-up-Pro-DJ-Link-Lighting-CDJ-3000-Tutorial-Series)
- [ShowKontrol (DJWORX)](https://djworx.com/pioneer-dj-gets-light-shows-showkontrol/)
- [Focusrite: Improving Latency on Mac](https://support.focusrite.com/hc/en-gb/articles/208736249-Improving-the-latency-of-your-Focusrite-interface-on-Mac)
- [Apple M1 + Audio Interface Latency (Gearspace)](https://gearspace.com/board/music-computers/1363715-apple-m1-audio-interface-latency.html)
- [VirtualDJ: XDJ-AZ Rear Panel](https://virtualdj.com/manuals/hardware/alphatheta/xdjaz/layout/frontrear.html)

---

### Question 4: Channel Separation / Deck Identification from Stereo Master Out

**Answer:** Full blind source separation of a DJ mix from stereo master alone is extremely difficult. However, when you have pre-analyzed reference tracks (which SCUE does), the problem becomes **dramatically more tractable** using mix-to-track subsequence alignment. This is an active area of academic research with proven results.

**Confidence: MEDIUM-HIGH** (strong academic foundation, but real-time implementation is novel)

**Detail:**

#### Approach 1: Mix-to-Track Subsequence Alignment (Most Promising)

**Key paper:** Kim & Choi, "A Computational Analysis of Real-World DJ Mixes using Mix-To-Track Subsequence Alignment" (ISMIR 2020)

This approach is directly applicable to SCUE because:
- It assumes you have the **original tracks** as reference (SCUE has pre-analyzed tracks with beat grids, waveforms, spectral features).
- It uses **subsequence Dynamic Time Warping (DTW)** on beat-synchronous features (MFCCs, chroma) to align reference tracks against the live mix.
- It extracts **cue points** (where tracks start/end in the mix), **transition lengths**, and **mix segmentation**.
- Features are designed to be **robust to tempo and key changes** that DJs apply.

**What it can determine:**
- Which known track is currently playing
- When a transition begins and ends
- Approximate mixing ratio during crossfades
- Tempo/key modifications applied by the DJ

**Limitation:** The published work is **offline** (post-hoc analysis of recorded mixes). Adapting to real-time requires a sliding-window approach, but the computational cost of DTW is manageable for a small library of candidate tracks.

#### Approach 2: Audio Fingerprinting (Track Identification Only)

Commercial services (AudD, ACRCloud, Shazam) demonstrate that audio fingerprinting works reliably even on:
- Mixed/overlapping audio
- Tempo-shifted content
- EQ'd and effects-processed audio

For SCUE's use case with a **private library** of pre-fingerprinted tracks:
- A local fingerprint database could identify which track is playing within seconds.
- Libraries like Chromaprint (open source, used by MusicBrainz) can generate fingerprints locally.
- This solves **identification** but not **mixing ratio estimation**.

**Related SCUE research:** See `research/research-findings-audio-fingerprinting-libraries.md`

#### Approach 3: Spectral Cross-Correlation with Pre-Analyzed Features

Using pre-analyzed spectral data from each track:
- Compute short-time spectral features of the live audio
- Cross-correlate against the known spectral envelope of each candidate track
- The correlation peak indicates which track is dominant and at what time offset

This is essentially a simplified version of Approach 1, trading accuracy for computational simplicity. It would work well for:
- Identifying the "primary" track (not in transition)
- Detecting transition onset (correlation with Track A drops while Track B rises)

#### Approach 4: Multi-Pass NMF (Academic, Less Practical for Real-Time)

**Paper:** "DJ Mix Transcription with Multi-Pass Non-Negative Matrix Factorization"

Uses NMF to decompose the mix spectrogram into components matching known tracks. Can extract arbitrary time-warping transformations including skips and loops. Computationally expensive; better suited for offline analysis.

#### Approach 5: Beat Position Correlation

Since SCUE has pre-analyzed **beat grids** and **phrase structures** for each track:
- The beat positions in the live audio can be compared against known beat grids
- During a transition, two beat grids will be present (possibly at different tempos if not beat-matched)
- Phase alignment between the live beats and known beat grids can identify which decks are active

This is complementary to the spectral approaches and could serve as a **low-cost confirmation signal**.

#### Practical Recommendation for SCUE

A **hybrid approach** combining multiple signals would be most robust:

1. **Audio fingerprinting** for initial track identification (confirms what Pro DJ Link reports, or works standalone for DLP hardware)
2. **Sliding-window cross-correlation** of spectral features against pre-analyzed tracks for continuous position tracking
3. **Beat grid correlation** as a lightweight confirmation signal
4. **Transition detection** via monitoring the correlation strength of the two most likely candidate tracks

This would allow SCUE to:
- Identify playing tracks even without reliable Pro DJ Link metadata (DLP hardware)
- Track playback position in real-time
- Detect transitions and estimate mixing ratios
- Work entirely from a stereo master out capture

**Sources:**
- [Mix-To-Track Subsequence Alignment (ISMIR 2020)](https://arxiv.org/abs/2008.10267)
- [Mix-To-Track Project Page](https://mir-aidj.github.io/djmix-analysis/)
- [DJ Mix Transcription with Multi-Pass NMF](https://hal.science/hal-04995821/document)
- [Music Source Separation (Wikipedia)](https://en.wikipedia.org/wiki/Music_Source_Separation)
- [Source Separation Tutorial](https://source-separation.github.io/tutorial/intro/src_sep_101.html)
- [Deep Audio Fingerprinting (GitHub)](https://github.com/ChrisNick92/deep-audio-fingerprinting)
- [ACRCloud](https://www.acrcloud.com/)
- [Methods and Datasets for DJ-Mix Reverse Engineering (ResearchGate)](https://www.researchgate.net/publication/349933466_Methods_and_Datasets_for_DJ-Mix_Reverse_Engineering)

---

## Summary & Implications for SCUE

### The Legacy CDJ Strategy is Viable
Connecting a CDJ-2000NXS2 to the XDJ-AZ gives beat-link full MetadataFinder/CrateDigger access for that player. This is a practical workaround for the DLP metadata problem, though it requires an extra audio cable and only covers one deck.

### Audio Capture is Straightforward
A simple USB audio interface (Scarlett 2i2 or equivalent) capturing the XDJ-AZ's balanced master or booth output provides high-quality audio with ~3-5ms input latency at 48kHz — more than adequate for any analysis SCUE needs to perform.

### Deck Identification from Audio is Feasible
The combination of pre-analyzed track data (which SCUE already has) and live audio capture enables a realistic path to track identification and position tracking that does not depend on Pro DJ Link metadata at all. This is the most significant finding — it means SCUE could work with **any** DJ hardware, not just Pioneer/AlphaTheta equipment.

### Recommended Next Steps
1. Evaluate whether a legacy CDJ workaround is worth the physical complexity vs. the audio-based approach
2. Prototype audio fingerprint matching against pre-analyzed track library
3. Prototype sliding-window spectral correlation for position tracking
4. Design the audio capture layer (Layer 0.5?) as an alternative/complement to the beat-link bridge
