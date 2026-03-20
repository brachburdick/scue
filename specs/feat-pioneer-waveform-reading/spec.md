# Spec: Pioneer Waveform Reading (pioneer-waveform-reading)

## Frozen Intent
- **Stakeholder:** Brach
- **Problem:** Waveform display requires SCUE analysis (3-8s per track). Pioneer USBs already contain pre-computed waveforms at 150 entries/second.
- **Desired outcome:** Read PWV3/PWV5/PWV7 waveform tags from USB ANLZ files during scan, store in cache, serve via API. Enables instant waveform display before SCUE analysis completes.
- **Non-goals:** Frontend rendering changes (separate task). Replacing SCUE analysis. Reading PWAV/PWV2/PWV4/PWV6 (lower priority tags).
- **Hard constraints:** Must use pyrekordbox for ANLZ parsing (ADR-013 Tier 1). Must store in pioneer_metadata cache. Must not break existing USB scan flow.
- **References:** ADR-014, research/findings-anlz-waveform-formats.md

## Specification

### What gets read

| Tag | File | Resolution | Data | Priority |
|-----|------|-----------|------|----------|
| PWV5 | .EXT | 150/sec, 2 bytes/entry | 3-bit RGB + 5-bit height | Primary (color detail) |
| PWV3 | .EXT | 150/sec, 1 byte/entry | 5-bit height + 3-bit intensity | Fallback (monochrome detail) |
| PWV7 | .2EX | 150/sec, 3 bytes/entry | 3-band (mid/high/low) heights | Bonus (CDJ-3000+) |

### Data flow

1. During USB scan, `_try_pyrekordbox()` reads .EXT and .2EX files alongside .DAT
2. Waveform data stored on `UsbTrack` as new fields
3. `store_pioneer_metadata()` persists waveform data to SQLite (as base64-encoded blobs)
4. `get_pioneer_metadata()` returns waveform data
5. New `GET /api/tracks/{fingerprint}/pioneer-waveform` endpoint serves decoded waveform arrays

### Storage format

Waveform data is stored as base64-encoded byte strings in SQLite TEXT columns:
- `waveform_pwv5`: base64 of raw PWV5 bytes (2 bytes per entry)
- `waveform_pwv3`: base64 of raw PWV3 bytes (1 byte per entry)
- `waveform_pwv7`: base64 of raw PWV7 bytes (3 bytes per entry)

Raw bytes are stored rather than decoded arrays to minimize storage overhead and keep decoding in the consumer (API endpoint / frontend).

### API response format

```json
{
  "fingerprint": "abc123...",
  "available": ["pwv5", "pwv3"],
  "pwv5": {
    "entries_per_second": 150,
    "total_entries": 45000,
    "data": [
      {"r": 5, "g": 3, "b": 7, "height": 24},
      ...
    ]
  },
  "pwv3": {
    "entries_per_second": 150,
    "total_entries": 45000,
    "data": [
      {"height": 18, "intensity": 5},
      ...
    ]
  }
}
```

Note: For large waveforms (45k entries for a 5-min track), the JSON array response could be ~2MB. An alternative binary endpoint may be needed later but JSON is fine for MVP.

### Edge cases

- .EXT file missing (older USB exports): skip waveform reading, no error
- .2EX file missing (pre-CDJ-3000 exports): skip PWV7, no error
- pyrekordbox not installed: skip gracefully (existing Tier 2 fallback has no waveform support)
- Empty waveform tags: store as empty, API returns `available: []`
- Track has SCUE waveform AND Pioneer waveform: both are available, frontend chooses

### Acceptance criteria

1. `_try_pyrekordbox()` reads PWV5, PWV3, and PWV7 tags when present
2. `UsbTrack` has `waveform_pwv5`, `waveform_pwv3`, `waveform_pwv7` fields (bytes)
3. Pioneer metadata cache stores and retrieves waveform blobs
4. API endpoint decodes and serves waveform data as JSON arrays
5. Existing USB scan tests pass without modification
6. New tests cover: waveform reading, storage, API endpoint, missing file cases

## Change Log
- 2026-03-20: Initial spec
