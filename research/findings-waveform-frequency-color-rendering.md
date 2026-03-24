# Waveform Frequency Band Visualization & Color Rendering

Research compiled 2026-03-24. Deep web research covering audio frequency bands, Pioneer/rekordbox waveform rendering, frequency weighting, color mapping, and amplitude scaling.

---

## 1. How Sound Frequency Bands Work

### 1.1 Standard Frequency Band Divisions

The audible spectrum (20 Hz -- 20 kHz) is conventionally divided into seven bands:

| Band | Range | Character |
|---|---|---|
| Sub-bass | 20--60 Hz | Felt more than heard; provides power/rumble |
| Bass | 60--250 Hz | Fundamental rhythm frequencies; determines fat/thin quality. Most bass in modern music sits 90--200 Hz |
| Low-mid | 250--500 Hz | Body of instruments; can become muddy if over-represented |
| Mid | 500 Hz--2 kHz | Core harmonic content of most instruments and vocals |
| Upper-mid | 2--4 kHz | Attack, presence of instruments; human hearing is most sensitive here (3--4 kHz peak) |
| Presence | 4--6 kHz | Clarity, definition, articulation of sound |
| Brilliance | 6--20 kHz | Entirely harmonics; sparkle, air, sibilance |

For DJ software 3-band splits, the typical crossover points are:
- **Low**: 20 Hz -- 200 Hz
- **Mid**: 200 Hz -- 4,000 Hz
- **High**: 4,000 Hz -- 20,000 Hz

These match standard DJ mixer EQ knob ranges (Allen & Heath, Pioneer DJM). Some implementations use slightly different points (250 Hz and 5 kHz are also common).

### 1.2 Logarithmic Nature of Human Hearing

Human hearing is fundamentally logarithmic in both frequency and amplitude perception:

- **Frequency**: We perceive pitch on a logarithmic scale. An octave (doubling of frequency) sounds like the same "distance" whether it's 100->200 Hz or 5000->10000 Hz. The cochlea's hair cells are distributed logarithmically along its length.
- **Amplitude**: A 10x increase in sound power (10 dB) is perceived as roughly a doubling of loudness. Our hearing spans approximately 120 dB of dynamic range (1 trillion:1 in power).

**Fletcher-Munson / Equal Loudness Contours (ISO 226)**

Fletcher and Munson (1933) measured how loud different frequencies must be to sound equally loud to listeners. Key findings:

- Human hearing is **most sensitive at 3--4 kHz** (the ear canal resonance frequency).
- At low listening levels, bass and treble must be significantly louder (in SPL) to sound as loud as midrange. At 40 phon, a 50 Hz tone needs ~30 dB more SPL than a 3 kHz tone to sound equally loud.
- At higher SPLs (80+ dB), the curves flatten -- all frequencies are perceived more equally.
- The modern standard is ISO 226:2003, which superseded the original Fletcher-Munson data.

**Implication for visualization**: If you display raw amplitude per band, bass will visually dominate because it carries more physical energy, even though it may not be perceptually louder.

### 1.3 Why Bass Carries More Energy

Music and natural sounds tend to follow a **pink noise (1/f) spectral profile**:
- Power spectral density is inversely proportional to frequency: S(f) ~ 1/f
- This means equal energy per octave. Since lower octaves span fewer Hz but higher octaves span many more Hz, the energy per-Hz is much higher at low frequencies.
- A bass note at 80 Hz physically moves more air (larger amplitude displacement) than a cymbal at 8 kHz, even if both sound equally loud.
- The 20--200 Hz band spans ~3.3 octaves. The 4000--20000 Hz band spans ~2.3 octaves. But the bass band's individual frequencies each carry significantly more power density.

**Result**: In an unweighted FFT spectrum or raw waveform amplitude, bass dominates. A kick drum at 80 Hz will produce a much taller waveform spike than a hi-hat at 10 kHz, even though the hi-hat may sound equally prominent to the ear.

### 1.4 Professional Audio Metering Weighting

| Weighting | Purpose | Characteristic |
|---|---|---|
| **A-weighting** | Approximate human hearing at low SPL (~40 phon) | Heavily attenuates below 500 Hz (-30 dB at 50 Hz), slight boost at 1--6 kHz. Standard for workplace noise regulations. |
| **C-weighting** | Approximate hearing at high SPL (~100 phon) | Nearly flat, slight rolloff below 50 Hz and above 8 kHz. Used for peak measurements and entertainment noise. |
| **Z-weighting** | Flat/unweighted | 10 Hz -- 20 kHz +/-1.5 dB. Raw measurement with no perceptual correction. |
| **K-weighting** | Perceptual loudness (ITU-R BS.1770) | Two-stage filter: (1) high shelf boosting ~+4 dB above 1.5 kHz, then (2) high-pass rolling off below ~100 Hz. Used for LUFS/LKFS loudness measurement in broadcast (EBU R128). |

**K-weighting** is the most relevant for modern loudness-aware applications. It was designed for the ITU-R BS.1770 standard and forms the basis of LUFS metering used by streaming services. It acknowledges that:
- Frequencies above ~1.5 kHz contribute more to perceived loudness (the shelf boost).
- Very low frequencies below ~100 Hz contribute less to perceived loudness (the high-pass).

---

## 2. Pioneer/Rekordbox Waveform Rendering

### 2.1 Waveform Modes

Pioneer supports three waveform display modes (availability varies by hardware):

| Mode | Colors | Supported Hardware |
|---|---|---|
| **BLUE** | Monochrome blue, brightness = frequency content | All CDJs since CDJ-2000 |
| **RGB** | Red=low, green/yellow=mid, blue=high | CDJ-2000NXS2, XDJ-1000MK2, XDJ-RX2, etc. |
| **3Band** | Blue=low, amber=mid, white=high | CDJ-3000, OPUS-QUAD, rekordbox 6+ |

### 2.2 BLUE Mode Encoding

The original/legacy waveform format. In the ANLZ file (PWV3 tag):
- **1 byte per entry**, 150 entries/second (one per half-frame at 75 fps)
- **Low 5 bits** (bits 0--4): height (0--31 pixels)
- **High 3 bits** (bits 5--7): "whiteness" -- controls color from dark blue (low frequency content) to bright white (high frequency content)

Visual interpretation: darker/more purple sections = more bass energy; brighter/whiter sections = more high frequency energy. The brightness encodes the spectral centroid or frequency balance, not separate bands.

### 2.3 RGB Color Waveform Encoding (PWV4, PWV5)

Introduced with the Nexus 2 line:

**PWV4 -- Color Preview (fixed-width)**:
- 6 bytes per entry, 1,200 columns total (7,200 bytes)
- Provides the overview/"birds-eye" waveform shown above the touch strip

**PWV5 -- Color Detail (variable-width)**:
- 2 bytes per entry (big-endian 16-bit integer), 150 entries/second
- Bit layout:
  - Bits 15--13: **Red** component (3 bits, 0--7)
  - Bits 12--10: **Green** component (3 bits, 0--7)
  - Bits 9--7: **Blue** component (3 bits, 0--7)
  - Bits 6--2: **Height** (5 bits, 0--31)
  - Bits 1--0: Unused

Color mapping:
- **Red** channel = low frequency energy
- **Green** channel = mid frequency energy
- **Blue** channel = high frequency energy

This means the RGB color at each waveform column encodes the frequency balance. A kick-heavy section appears red; a vocal section appears green/yellow; hi-hats appear blue/cyan.

### 2.4 THREE_BAND Waveform Encoding (PWV6, PWV7)

Introduced with CDJ-3000. Stored in the `.2EX` (second extended analysis) file:

**PWV6 -- 3-Band Preview (fixed-width)**:
- 3 bytes per entry, 1,200 columns (3,600 bytes total)
- Byte order per entry: **mid**, **high**, **low** (not low/mid/high!)

**PWV7 -- 3-Band Detail (variable-width)**:
- 3 bytes per entry, 150 entries/second
- Same byte order: **mid**, **high**, **low**
- Each byte is a height value (0--255)

**Rendering approach for 3-Band**:

The three bands are drawn on the **same axis** (overlapping), not stacked:
1. **Low** (dark blue) is drawn first
2. **Mid** (amber/brown) is drawn on top -- where low and mid overlap, a **brown** blend color appears
3. **High** (white) is drawn last, on top of everything -- it obscures any low or mid underneath

This painter's-algorithm approach means:
- Pure bass-heavy sections appear blue
- Sections with both bass and mid show brown blending
- High-frequency transients (snares, hats) appear as white spikes on top
- The overlap rendering naturally creates visual differentiation without explicit alpha blending

### 2.5 Overview vs Detail Waveforms

| Aspect | Overview (Preview) | Detail |
|---|---|---|
| Width | Fixed: 1,200 columns for entire track | Variable: 150 columns/second |
| Purpose | Track navigation (minimap above jog wheel or touch strip) | Scrolling view around playhead |
| Resolution | Entire track compressed into 1,200 points | Half-frame resolution (1/150th second) |
| Formats | PWV4 (color), PWV6 (3-band) | PWV3 (blue), PWV5 (color), PWV7 (3-band) |

### 2.6 How Pioneer Normalizes Frequency Bands

Pioneer's exact normalization algorithm is not publicly documented. However, from the reverse-engineered data:

- Each band height value in the 3-band format uses a full byte (0--255), meaning each band is **independently scaled** to its own range during rekordbox analysis.
- The RGB format uses only 3 bits per color channel (0--7), which is coarse but enough to show relative balance.
- Pioneer likely applies **per-band normalization** during the analysis pass: each band's contribution is normalized relative to its own peak or average energy across the track, rather than using raw absolute amplitude. This prevents bass from always dominating.
- The amplitude normalization (waveform height) appears to be done per-track, scaling the tallest peak to the full display height. CDJ-loaded waveforms show more consistent normalization than the rekordbox desktop preview.

---

## 3. Frequency Band Weighting for Visual Representation

### 3.1 The Core Problem

In raw FFT data, bass frequencies carry far more energy than highs. If you naively sum energy in the 20--200 Hz band vs 4000--20000 Hz band, bass will dominate by 20--40 dB depending on the content. Direct visualization of this makes for a waveform that is always "bass-colored."

### 3.2 Common Compensation Approaches

**Per-band independent normalization**: Each band (low/mid/high) is normalized to its own peak or running average. This is what Pioneer appears to do. Each band's height value represents that band's energy relative to that band's own maximum, not relative to other bands.

**Spectral slope compensation (pink noise tilt)**: Apply a +3 dB/octave tilt to compensate for the natural 1/f rolloff of music. A spectrum analyzer with 3 dB/octave slope renders pink noise as flat. For audio visualization, this means applying a frequency-dependent gain that boosts highs relative to lows:
- Gain(f) = 10 * log10(f / f_ref) dB, where f_ref is a reference frequency
- Or equivalently, multiply amplitude by sqrt(f / f_ref)
- Some analyzers use 4.5 dB/octave for modern music with more high-frequency energy

**Perceptual weighting (A/K-weighting)**: Apply the A-weighting or K-weighting curve before computing band energies. This matches human loudness perception:
- Attenuates sub-bass heavily
- Slight boost around 2--4 kHz
- K-weighting is gentler and more modern

**Logarithmic frequency binning**: Use logarithmically-spaced frequency bins (octave or 1/3-octave bands) rather than linear FFT bins. Since an octave at bass (100--200 Hz) spans 100 Hz but an octave at treble (5000--10000 Hz) spans 5000 Hz, linear bins over-represent bass. Log binning gives each octave equal visual weight.

### 3.3 How Professional DJ Software Handles This

**Pioneer/rekordbox**: Per-band normalization with independent byte ranges per band. 3-band mode uses overlapping painter's algorithm rendering.

**Serato**: Uses red=bass, green=mid, blue=high. The color intensity per-band appears independently normalized. Serato also offers "EQ Colored Waveform" mode where the waveform colors respond to the EQ knob positions in real time (removing bass removes the red).

**Traktor**: Offers a "spectrum" waveform option with similar frequency-to-color mapping. Uses the same general red/green/blue convention.

**VirtualDJ**: Offers 5 different colored waveform configurations. Supports stem visualization where frequency bands can be grayed out.

### 3.4 Per-Channel Energy Normalization (PCEN)

A more sophisticated technique from machine learning audio research:
- Applies automatic gain control per frequency channel
- Enhances transient events while discarding stationary noise
- Formula: PCEN(t,f) = (E(t,f) / (eps + M(t,f))^alpha + delta)^r - delta^r
- Where M is a smoothed version of E (temporal integration)
- Useful for ML-oriented visualization but likely overkill for DJ waveforms

---

## 4. Color Mapping Approaches

### 4.1 The Three Major Conventions

| Software | Low/Bass | Mid | High/Treble |
|---|---|---|---|
| **Pioneer RGB** | Red | Green/Yellow | Blue |
| **Pioneer 3-Band** | Dark Blue | Amber | White |
| **Serato** | Red | Green | Blue |
| **Traktor** | Red | Green | Blue |

Note the interesting divergence: Pioneer 3-Band inverts the RGB convention by using blue for bass. This is arguably more intuitive (blue = deep/cool = bass, white = bright = treble) but conflicts with the Serato/Traktor convention.

### 4.2 RGB Color Space for 3-Band Mapping

The simplest approach: map each band to an RGB channel directly:
```
R = low_energy (normalized 0-255)
G = mid_energy (normalized 0-255)
B = high_energy (normalized 0-255)
```

Produces: red = bass-heavy, green = mid-heavy, blue = treble-heavy, yellow = bass+mid, cyan = mid+high, white = all frequencies present, dark = silence.

**Advantages**: Simple, computationally trivial, well-established convention.
**Disadvantages**: Perceptually uneven -- human eyes are most sensitive to green, least to blue. A "mid-heavy" section looks brighter than a "treble-heavy" section even at the same energy levels. Red and blue have lower luminance contribution.

### 4.3 HSL Color Space Mapping

An alternative approach mapping frequency balance to hue:
```
hue = weighted_spectral_centroid mapped to 0-360 degrees
saturation = frequency_concentration (pure tone = saturated, noise = desaturated)
lightness = amplitude
```

**Advantages**: Perceptually more uniform; hue differences are easier to distinguish than RGB channel balance. Decouples "what frequency" from "how loud."
**Disadvantages**: More complex computation; the hue wheel doesn't have an obvious natural mapping to frequency.

A practical HSL approach:
- Hue 0 (red) = bass, Hue 120 (green) = mid, Hue 240 (blue) = high
- Or continuously: hue = (a + b * log2(f / f_ref)) mod 360
- Saturation high = one band dominates, low = broadband content
- Lightness = overall amplitude

### 4.4 Pioneer's 3-Band Overlap Rendering

Pioneer's 3-Band approach is notable because it avoids the need for color blending entirely:

1. Draw low band (blue) at its height
2. Draw mid band (amber) at its height -- overlapping produces brown naturally
3. Draw high band (white) at its height -- overlapping shows as white on top

This is effectively a **back-to-front painter's algorithm** with hardcoded colors per layer. The visual result:
- Bass drops = tall blue columns
- Vocal/synth sections = amber with blue underneath
- Hi-hat patterns = white spikes overlaid on colored content
- Full-spectrum moments = white on top, brown/blue underneath

### 4.5 Alpha/Opacity Layered Approach

An extension of Pioneer's method using proper alpha compositing:
```
For each column:
  background = black
  draw low band with color (0, 0, 255) at alpha proportional to low_energy
  draw mid band with color (255, 180, 0) at alpha proportional to mid_energy
  draw high band with color (255, 255, 255) at alpha proportional to high_energy
```

With alpha blending (Porter-Duff "over" operator):
```
C_out = C_fg * alpha_fg + C_bg * (1 - alpha_fg)
```

This allows smooth transitions between band dominance and produces visually pleasing gradients where bands overlap, rather than hard painter's-algorithm occlusion.

### 4.6 Preserving Detail Across the Spectrum

Techniques to ensure all bands remain visible:
- **Minimum brightness floor**: Ensure each band has a minimum opacity/brightness so it's never invisible, even if its energy is low.
- **Gamma correction per band**: Apply different gamma curves to each band to expand the visible range of the weaker band.
- **Additive blending**: Instead of alpha compositing, add the color channels together (clamping to max). This ensures that a quiet high-frequency band still shows up even when bass is dominant.
- **Independent normalization with separate display**: Show each band as a separate sub-waveform (stacked vertically) rather than overlaid. This guarantees all three bands are always fully visible.

---

## 5. Amplitude Scaling

### 5.1 Linear vs Logarithmic (dB) Display

**Linear amplitude**: The raw sample value or energy value is mapped directly to pixel height. This is what you get from a direct FFT magnitude.
- Pro: Intuitive for editing, loud sections visually dominate.
- Con: Low-level detail is invisible. A -40 dB signal occupies only 1% of the display height.

**Logarithmic (dB) amplitude**: Convert to decibels before display: dB = 20 * log10(amplitude).
- Pro: Low-level detail becomes visible; matches human loudness perception better.
- Con: Very quiet sections may be over-emphasized; noise floor becomes prominent.

**Hybrid/sqrt scaling**: A common compromise is to apply a power function: display_height = amplitude^gamma, where gamma is typically 0.3--0.5. This provides some compression without the full dB scale.
- `amplitude^0.5` (square root) is a common choice -- provides moderate compression
- `amplitude^0.33` is more aggressive, closer to dB behavior

### 5.2 Dynamic Range Compression for Visualization

The key formula for log compression in visualization:
```
compressed = log(1 + gamma * value) / log(1 + gamma)
```

Where gamma controls compression strength:
- gamma = 1: mild compression
- gamma = 10: moderate compression
- gamma = 100: heavy compression (quiet signals become very visible)

This approach:
- Maps 0 to 0 and 1 to 1 (preserves endpoints)
- Expands quiet values while compressing loud values
- The gamma parameter allows tuning the compression amount

### 5.3 Peak vs RMS Display

**Peak**: Shows the maximum instantaneous amplitude in each display column's time window. Good for showing transients (kick drums, snares). Most waveform editors use this.

**RMS**: Root Mean Square -- shows the average energy in each column's window. Better represents perceived loudness. Many DAWs show RMS as a filled inner waveform with peak as the outer envelope.

**Combined display (Audacity-style)**: Draw the peak amplitude as the outer waveform boundary, and the RMS amplitude as a filled inner region. This shows both transient peaks and sustained energy simultaneously.

For DJ waveforms, **peak display is standard** -- it shows drum hits and transients clearly, which is what DJs need for beat-matching and visual mixing.

### 5.4 How Pioneer Handles Amplitude Normalization

- Pioneer/rekordbox performs **per-track normalization** during analysis. Each track's waveform is scaled so its loudest point fills the available display height.
- The height value in the waveform data (5 bits in PWV3/PWV5, full byte in PWV6/PWV7) represents the normalized amplitude for that time slice.
- Rekordbox also offers a "loudness normalization" feature (since v4.2.1) that writes ReplayGain-style tags to adjust playback volume, but this is separate from waveform display normalization.
- CDJ hardware appears to apply its own normalization when rendering the waveform data, which can differ from the rekordbox desktop preview. CDJ rendering tends to be more consistent.
- The 5-bit height field (0--31) in the legacy formats means only 32 distinct amplitude levels. The 3-band format's full byte (0--255) provides much finer granularity.

### 5.5 Recommendations for a Configurable Renderer

Based on all findings, a configurable waveform renderer should offer:

**Amplitude scaling options**:
- Linear (raw)
- Square root (moderate compression)
- Logarithmic/dB (maximum detail)
- Configurable gamma: `height = amplitude^gamma`

**Frequency band normalization options**:
- Global normalization (all bands share one scale -- bass dominates)
- Per-band normalization (each band scaled independently -- Pioneer style)
- Weighted normalization (apply A/K-weighting before computing band energy)
- Pink noise compensation (+3 dB/octave tilt)

**Color mapping options**:
- Pioneer RGB (red=low, green=mid, blue=high)
- Pioneer 3-Band (blue=low, amber=mid, white=high with overlap rendering)
- Serato-style (red=low, green=mid, blue=high)
- Monochrome with brightness=frequency (Pioneer BLUE mode)
- Configurable per-band colors

**Rendering mode options**:
- Overlapping (painter's algorithm, Pioneer 3-Band style)
- Alpha-blended layers
- Additive blending
- Stacked (bands shown separately, vertically)
- Single-color with frequency->brightness mapping

---

## Sources

- [Teach Me Audio - Audio Spectrum](https://www.teachmeaudio.com/mixing/techniques/audio-spectrum)
- [Audible Genius - Audio Frequency Range Bands Chart](https://audiblegenius.com/blog/audio-frequency-range-bands-chart)
- [Wikipedia - Equal-loudness contour](https://en.wikipedia.org/wiki/Equal-loudness_contour)
- [iZotope - Fletcher Munson Curve](https://www.izotope.com/en/learn/what-is-fletcher-munson-curve-equal-loudness-curves)
- [LANDR - Fletcher-Munson Curves](https://blog.landr.com/fletcher-munson-curves/)
- [Wikipedia - A-weighting](https://en.wikipedia.org/wiki/A-weighting)
- [Wikipedia - LUFS](https://en.wikipedia.org/wiki/LUFS)
- [NTi Audio - Frequency Weightings](https://www.nti-audio.com/en/support/know-how/frequency-weightings-for-sound-level-measurements)
- [Deep Symmetry - DJ Link Ecosystem Analysis (ANLZ format)](https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/anlz.html)
- [AlphaTheta Help - Waveform Colors (BLUE/RGB/3Band)](https://support.pioneerdj.com/hc/en-us/articles/8113178546201)
- [Pioneer DJ Forum - 3-Band Waveform Experience](https://forums.pioneerdj.com/hc/en-us/community/posts/900001415406-3-band-waveform-what-s-your-experience)
- [Serato Support - Main Waveform Display](https://support.serato.com/hc/en-us/articles/224969307-Main-Waveform-Display)
- [Digital DJ Tips - Reading Colours in DJ Waveforms](https://www.digitaldjtips.com/your-questions-how-do-i-read-the-colours-in-dj-waveforms/)
- [Hot Cue DJ - The Secret Language of Waveforms](https://reallychrism.substack.com/p/the-secret-language-of-waveforms)
- [Audacity Manual - Waveform Display](https://manual.audacityteam.org/man/audacity_waveform.html)
- [Audio Labs Erlangen - Logarithmic Compression](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C3/C3S1_LogCompression.html)
- [Medium - Spectrum Analyzer Slopes in Audio Mixing](https://medium.com/ai-music/spectrum-analyzer-slopes-in-audio-mixing-d6df8892ea3)
- [pyrekordbox - Analysis Files Format](https://pyrekordbox.readthedocs.io/en/latest/formats/anlz.html)
- [Wikipedia - Pink Noise](https://en.wikipedia.org/wiki/Pink_noise)
- [DeeJay Plaza - Waveform Colors in Rekordbox](https://www.deejayplaza.com/en/articles/color-waveform-rekordbox)
