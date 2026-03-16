# Test Audio Fixtures

Place audio files for testing here. These are NOT committed to git (see .gitignore).

## Recommended test set (minimum 5 tracks)

Choose tracks that represent different EDM genres to stress-test the classifier:
- 1× melodic techno (120–130 BPM, typical 32-bar phrases)
- 1× dubstep (140 BPM, irregular drops)
- 1× house (126 BPM, 8-bar loops, minimal arrangement)
- 1× DnB (174 BPM, fast breakdowns)
- 1× trance (138 BPM, long builds)

## Reference labels

For each test track, create a sidecar JSON file with the same name
and a `.labels.json` extension containing hand-labeled section boundaries:

```json
{
  "track": "my_track.mp3",
  "bpm": 128.0,
  "sections": [
    { "label": "intro",     "start": 0.0,   "end": 32.0  },
    { "label": "build",     "start": 32.0,  "end": 64.0  },
    { "label": "drop",      "start": 64.0,  "end": 128.0 },
    { "label": "breakdown", "start": 128.0, "end": 160.0 },
    { "label": "build",     "start": 160.0, "end": 192.0 },
    { "label": "drop",      "start": 192.0, "end": 256.0 },
    { "label": "outro",     "start": 256.0, "end": 288.0 }
  ]
}
```

## Milestone 1 accuracy target

≥80% of section boundaries within 1 bar of the hand-labeled reference.
