# Test Audio Assets

Binary audio files live here but are gitignored. This manifest describes
what a tester needs to populate this directory for full QA coverage.

Audio files are NOT checked in. Copy or generate them locally.
Synthetic generators exist in `tests/test_layer1/test_analysis_edge_cases.py`.

---

## Directory Layout

```
audio/
├── full-tracks/          # Complete songs (3–7 min)
├── loops/                # 4–32 bar loops
├── one-shots/            # Single hits, transients
├── stems/                # Pre-separated components
├── edge-cases/           # Degenerate, adversarial, or unusual inputs
└── pioneer/              # Tracks with known rekordbox analysis for enrichment testing
```

---

## 1. Full Tracks

Complete songs for end-to-end pipeline testing: fingerprint → analysis → sections → events → waveform.

### Currently populated (2026-03-20)

10 real tracks from the royalty-free library, placed here for manual end-to-end QA.
Each track also has a rekordbox-analyzed copy in `pioneer/` (see §6).

| File | Remixer / Artist | Genre context |
|------|-----------------|---------------|
| `Apashe - Duel Of The Fates.mp3` | Apashe | Cinematic bass |
| `Eon - You're Immortal (Trap Remix).mp3` | Eon | Trap |
| `F.O.O.L - Duality (VIP).mp3` | F.O.O.L | Electro house |
| `Fugees - Ready or Not (Jaenga Flip).mp3` | Jaenga | Bass / flip |
| `Imagine Dragons - Radioactive (Spoone Flip).mp3` | Spoone | Dubstep flip |
| `John Summit - Eat The Bass (WARCER Remix).mp3` | WARCER | Tech house remix |
| `Kaivon - Think of Me.mp3` | Kaivon | Melodic bass |
| `Rival - Revival (w Philip Strand).mp3` | Rival | Future bass |
| `SLIP - Elliot Moss (HABBIT4T REMIX).mp3` | HABBIT4T | Midtempo |
| `nikko - PUSHINN.mp3` | nikko | Bass |

**Source:** `/Users/brach/Documents/RoyaltyFreeMusicSamples/post-hibernation/`
These are the un-analyzed originals. To repopulate, copy from the source path above.

### By genre (section structure & energy profile vary)

| Slot | Genre | What it tests | Example characteristics |
|------|-------|---------------|----------------------|
| `full-tracks/edm-drop-heavy.wav` | Dubstep / Bass | Hard drops, fakeouts, silence gaps | Clear intro→build→drop→breakdown→drop→outro |
| `full-tracks/edm-progressive.wav` | Progressive House | Long builds, gradual energy | 16-32 bar sections, slow energy ramp |
| `full-tracks/edm-minimal.wav` | Tech House / Minimal | Subtle transitions, steady energy | Short sections, low energy variance |
| `full-tracks/edm-dnb.wav` | Drum & Bass | Fast tempo (170+ BPM), breakbeats | Tests BPM range, beat grid at high tempo |
| `full-tracks/edm-halftime.wav` | Halftime / Midtempo | ~75-85 BPM, heavy sub-bass | Tests low BPM detection, section labeling |
| `full-tracks/edm-trance.wav` | Trance | Very long builds, euphoric drops | 64-bar sections, consistent phrasing |

### By arrangement pattern

| Slot | Pattern | What it tests |
|------|---------|---------------|
| `full-tracks/pattern-standard-edm.wav` | Intro→Build→Drop→Break→Drop→Outro | Happy path for flow model |
| `full-tracks/pattern-double-drop.wav` | Build→Drop→Drop (no breakdown) | Back-to-back drops without recovery |
| `full-tracks/pattern-long-intro.wav` | 64+ bar intro | Section detector patience |
| `full-tracks/pattern-no-drop.wav` | Melodic with no clear drop | Flow model with missing expected labels |
| `full-tracks/pattern-fakeout.wav` | Build→Fakeout→Build→Real Drop | Fakeout detection accuracy |
| `full-tracks/pattern-irregular-phrase.wav` | 7-bar or 15-bar phrases | Snap-to-grid with irregular phrase flagging |

---

## 2. Loops

Short repeating segments for focused detector testing.

| Slot | Content | Duration | What it tests |
|------|---------|----------|---------------|
| `loops/kick-4bar-128bpm.wav` | Kick on every beat | 4 bars | Beat grid extraction, BPM lock |
| `loops/four-on-floor-8bar.wav` | Kick+hat+snare | 8 bars | Drum pattern detection, hihat classification |
| `loops/breakbeat-4bar.wav` | Syncopated drums | 4 bars | Non-4-on-floor pattern detection |
| `loops/buildup-riser-16bar.wav` | Rising noise sweep | 16 bars | Riser event detection, duration tracking |
| `loops/breakdown-pad-8bar.wav` | Sustained pads only | 8 bars | Low energy region, section labeling as "breakdown" |
| `loops/arp-sequence-8bar.wav` | Arpeggiated synth | 8 bars | Arp note detection, periodicity |
| `loops/vocal-chop-4bar.wav` | Chopped vocal hits | 4 bars | Vocal event detection vs drum false-positive |
| `loops/bass-wobble-4bar.wav` | Wobble bass (LFO) | 4 bars | Spectral centroid oscillation, not confused with riser |
| `loops/filter-sweep-8bar.wav` | LP filter opening | 8 bars | Sweep detection via centroid tracking |
| `loops/silence-with-hits.wav` | Sparse hits in silence | 4 bars | Onset detection in quiet context |

---

## 3. One-Shots

Single transient hits for percussion classifier testing.

| Slot | Content | What it tests |
|------|---------|---------------|
| `one-shots/kick-acoustic.wav` | Acoustic kick drum | Kick classification baseline |
| `one-shots/kick-808.wav` | 808 sub kick | Low-freq kick, long tail |
| `one-shots/kick-distorted.wav` | Distorted / clipped kick | Kick detection with spectral spread |
| `one-shots/snare-acoustic.wav` | Acoustic snare | Snare classification baseline |
| `one-shots/snare-clap-layer.wav` | Snare + clap layered | Snare vs clap disambiguation |
| `one-shots/clap-clean.wav` | Isolated clap | Clap classification baseline |
| `one-shots/hihat-closed.wav` | Closed hihat | Hihat type: closed |
| `one-shots/hihat-open.wav` | Open hihat | Hihat type: open, decay length |
| `one-shots/crash.wav` | Crash cymbal | Should NOT classify as hihat |
| `one-shots/riser-white-noise.wav` | White noise riser (~4s) | Riser detection, duration measurement |
| `one-shots/impact-hit.wav` | Downbeat impact/boom | Impact event type |
| `one-shots/reverse-cymbal.wav` | Reversed cymbal swell | Reverse cymbal event detection |
| `one-shots/stab-synth.wav` | Short synth stab | Stab event vs kick false-positive |

---

## 4. Stems

Pre-separated components for testing stem-aware detectors (post-Demucs).

| Slot | Content | What it tests |
|------|---------|---------------|
| `stems/drums-isolated.wav` | Drum stem from Demucs | Percussion detector on clean input |
| `stems/bass-isolated.wav` | Bass stem | Bass presence detection, sub energy |
| `stems/vocals-isolated.wav` | Vocal stem | Vocal region detection |
| `stems/other-isolated.wav` | Melody/synth stem | Arp/riser/stab detection on clean input |
| `stems/drums-plus-bass.wav` | Drums + bass mixed | Partial separation quality |
| `stems/full-mix-matching.wav` | Original full mix for the above stems | Round-trip: stems should reconstruct to this |

---

## 5. Edge Cases

Degenerate, adversarial, or boundary inputs that should not crash the pipeline.

| Slot | Content | What it tests |
|------|---------|---------------|
| `edge-cases/silence-10s.wav` | Pure digital silence | No crash, near-zero energy, empty beat grid OK |
| `edge-cases/silence-01s.wav` | 100ms silence | Minimum viable input, no crash |
| `edge-cases/white-noise-10s.wav` | Pure white noise | No meaningful beats, should not crash |
| `edge-cases/sine-440hz-5s.wav` | Single 440Hz tone | No transients, BPM may be empty |
| `edge-cases/dc-offset.wav` | Audio with DC bias | Feature extraction robustness |
| `edge-cases/clipping-distorted.wav` | Heavily clipped full-scale | Peak handling, no NaN/Inf |
| `edge-cases/very-short-05s.wav` | 0.5 second audio | Minimum duration handling |
| `edge-cases/very-long-20min.wav` | 20+ minute track | Memory / performance, array sizing |
| `edge-cases/tempo-change.wav` | Track with BPM shift mid-song | tempo_stable=false, beat grid divergence |
| `edge-cases/tempo-60bpm.wav` | Very slow (60 BPM) | Low BPM boundary |
| `edge-cases/tempo-200bpm.wav` | Very fast (200 BPM) | High BPM boundary, half-time confusion |
| `edge-cases/key-change.wav` | Modulation mid-track | Key detection confidence drop |
| `edge-cases/stereo-mono-mismatch.wav` | Mono audio in stereo container | Channel handling |
| `edge-cases/spoken-word.wav` | Speech, no music | Should not produce musical analysis |

---

## 6. Pioneer Enrichment

Tracks with KNOWN rekordbox analysis for testing the enrichment merge path.
Must be exported from rekordbox with ANLZ files alongside.

### Currently populated (2026-03-20)

10 tracks copied from a rekordbox USB export backup. These are the same 10 songs
as `full-tracks/` (see §1) but sourced from the rekordbox-organized USB structure,
meaning rekordbox has already analyzed them (beatgrid, waveform, phrase data, etc.).

The corresponding ANLZ files (`.DAT`, `.EXT`, `.2EX`) live in the USB backup at
`/Users/brach/Documents/skald usb backup 3.16.26/PIONEER/USBANLZ/P018/` — each
track has a hex-named subdirectory there. The rekordbox library database is at
`.../PIONEER/rekordbox/exportLibrary.db`. These are NOT yet copied into the fixture
directory — only the audio files are present. To fully test the enrichment pipeline,
the matching ANLZ files will need to be identified (via the rekordbox DB) and placed
alongside each track.

**Source:** `/Users/brach/Documents/skald usb backup 3.16.26/Contents/{Artist}/UnknownAlbum/`

**Note:** The source library (post-hibernation) and USB export use different directory
structures. See LEARNINGS.md "Music library directory structure mismatch" for details
and future unification plans.

### Target slots (not yet populated)

| Slot | Content | What it tests |
|------|---------|---------------|
| `pioneer/track-with-anlz/` | Track + `.DAT`/`.EXT` ANLZ files | Full enrichment pipeline |
| `pioneer/track-cues-and-loops/` | Track with hot cues + loops set | Cue point parsing, merge |
| `pioneer/track-phrases/` | Track with phrase analysis | Phrase analysis parsing |
| `pioneer/track-corrected-grid/` | Track with hand-corrected beatgrid | Pioneer beatgrid override (ADR-001) |
| `pioneer/track-key-mismatch/` | Track where Pioneer key ≠ analysis key | Divergence logging |

---

## Format Matrix

Each slot above defaults to WAV. For format-specific testing, provide these variants:

| Format | Extension | Codec | Bit Depth / Rate | What it tests |
|--------|-----------|-------|-------------------|---------------|
| WAV PCM 16-bit | `.wav` | PCM | 16-bit / 44.1kHz | Baseline reference |
| WAV PCM 24-bit | `.wav` | PCM | 24-bit / 44.1kHz | High bit depth handling |
| WAV PCM 32-float | `.wav` | IEEE float | 32-bit / 44.1kHz | Float sample handling |
| WAV 48kHz | `.wav` | PCM | 16-bit / 48kHz | Non-44.1k sample rate |
| WAV 96kHz | `.wav` | PCM | 24-bit / 96kHz | High sample rate downsampling |
| MP3 320 | `.mp3` | LAME | 320 kbps | Lossy high quality |
| MP3 128 | `.mp3` | LAME | 128 kbps | Lossy low quality — artifacts |
| MP3 VBR | `.mp3` | LAME VBR | ~190 kbps avg | Variable bitrate seeking |
| FLAC | `.flac` | FLAC | 16-bit / 44.1kHz | Lossless compressed |
| FLAC 24-bit | `.flac` | FLAC | 24-bit / 96kHz | High-res lossless |
| AIFF | `.aiff` | PCM | 16-bit / 44.1kHz | macOS-native format |
| AAC | `.m4a` | AAC-LC | 256 kbps | iTunes/Apple format |
| OGG Vorbis | `.ogg` | Vorbis | Q6 (~192 kbps) | Open-source lossy |

### Format test tracks

Place in a `formats/` subdirectory. Use the SAME source audio encoded to each format
so fingerprint/analysis differences are purely format-induced.

```
audio/formats/
├── reference.wav           # 16-bit 44.1kHz PCM — the ground truth
├── reference-24bit.wav
├── reference-32float.wav
├── reference-48k.wav
├── reference-96k.wav
├── reference-320.mp3
├── reference-128.mp3
├── reference-vbr.mp3
├── reference.flac
├── reference-24bit-96k.flac
├── reference.aiff
├── reference.m4a
└── reference.ogg
```

---

## What SCUE Does With Each Category

| Category | Pipeline Stage | Detectors Exercised |
|----------|---------------|---------------------|
| **Full tracks** | End-to-end: fingerprint → analysis → storage → retrieval | All: sections, snap, flow model, features, tonal, percussion, waveform |
| **Loops** | Focused detector unit testing | Individual detectors in isolation |
| **One-shots** | Percussion classifier training/validation | percussion_heuristic, percussion_rf |
| **Stems** | Post-Demucs detector accuracy | Percussion on clean drum stem, tonal on other stem |
| **Edge cases** | Robustness / no-crash guarantees | All detectors — none should panic |
| **Pioneer** | Enrichment merge + divergence logging | enrichment.py, anlz_parser.py, divergence.py |
| **Formats** | Codec robustness, fingerprint stability | fingerprint.py, librosa loader, all downstream |

---

## Generating Synthetic Assets

For one-shots and edge cases, prefer generating programmatically over sourcing.
Extend `tests/test_layer1/test_analysis_edge_cases.py` helpers:

```python
import numpy as np
import soundfile as sf

SR = 44100

def sine(duration, freq=440.0):
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    return np.sin(2 * np.pi * freq * t).astype(np.float32)

def silence(duration):
    return np.zeros(int(SR * duration), dtype=np.float32)

def noise(duration, seed=42):
    rng = np.random.default_rng(seed)
    return rng.standard_normal(int(SR * duration)).astype(np.float32)

def kick(decay=0.15, pitch_start=150, pitch_end=40):
    n = int(SR * decay)
    t = np.linspace(0, decay, n, endpoint=False)
    freq = np.linspace(pitch_start, pitch_end, n)
    phase = np.cumsum(2 * np.pi * freq / SR)
    env = np.exp(-t * 20)
    return (np.sin(phase) * env).astype(np.float32)

# Write: sf.write("one-shots/kick-808.wav", kick(), SR)
```

## Priority

If you can only populate a subset, this order gives the most coverage:

1. **One full EDM track** (`full-tracks/edm-drop-heavy.wav`) — exercises entire pipeline
2. **Edge cases** (silence, noise, sine, very-short) — prevents crashes
3. **Format variants** of one track — catches codec bugs
4. **One-shots** (kick, snare, hihat) — percussion classifier baseline
5. **A Pioneer export** with ANLZ files — enrichment path
6. Everything else
