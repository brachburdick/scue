# Skill: Pioneer Hardware / Rekordbox / ANLZ

> **When to use:** Any task involving Pioneer CDJ/XDJ hardware, Rekordbox database, ANLZ file parsing, USB library scanning, or Pioneer metadata enrichment.

---

## Stack & Environment

- pyrekordbox for Rekordbox database reading
- rbox for USB library scanning (Device Library Plus format, ADR-012)
- Pure Python ANLZ parser at `scue/layer1/anlz_parser.py` (ADR-013)
- USB scanner at `scue/layer1/usb_scanner.py`
- Enrichment logic at `scue/layer1/enrichment.py`

## Architecture

```
Pioneer USB/SD → ANLZ files + exportLibrary.db → Parser → Enrichment → TrackAnalysis (JSON)
```

## Key Concepts

### Pro DJ Link Protocol
- UDP broadcast on port 50000-50002
- Devices announce themselves, exchange status, and stream beat data
- beat-link (Java) is the primary listener — see `skills/beat-link-bridge.md`

### ANLZ Files
- Binary format containing beat grids, cue points, waveforms
- Located on Pioneer USB/SD media alongside audio files
- Two formats: classic (`.DAT`) and Device Library Plus (`.2EX`)

### Rekordbox Database
- `exportLibrary.db` on USB contains track metadata
- Read via rbox for XDJ-AZ and other DLP devices

### Pioneer Beatgrid as Source of Truth
- Pioneer beatgrids override librosa-derived beat tracking (ADR-001)
- Original SCUE analysis is preserved and versioned
- Divergence between Pioneer and SCUE is logged, never silently resolved

## Known Gotchas

- **rbox Rust panics:** rbox's Rust-based ANLZ parser can panic on Device Library Plus files. These panics are uncatchable in Python and crash the process. Use the pure Python parser instead (ADR-013).
- **MetadataFinder on XDJ-AZ:** beat-link's MetadataFinder does not work with Device Library Plus format. Read metadata from `exportLibrary.db` via rbox instead (ADR-012).
- **XDJ-AZ track change detection:** Unlike CDJ-2000NXS2, XDJ-AZ does not transition `trackType` through `NO_TRACK` on track changes. Must combine multiple signals (CDJ status, track metadata change) for reliable detection.
- **Pioneer data enrichment:** When enriching SCUE analysis with Pioneer data, NEVER overwrite — merge and log any divergence.

## Hardware-Specific Reference

### XDJ-AZ Specifics
- Reports BLUE-style waveforms (single color channel), not THREE_BAND (RGB)
- Reports garbage BPM (e.g., 658.63) when no track loaded — guard with `isTrackLoaded()`
- Uses standard Pro DJ Link (not DLP/NFS like Opus Quad)
- Network interface for DJ Link must be configured in `bridge.yaml` (not auto-detected)
- macOS link-local route fix: `sudo route add -host 169.254.255.255 -interface <interface>`

### Opus Quad / DLP Devices
- No dbserver — requires CrateDigger NFS path for metadata/waveforms
- WaveformFinder and other Finders that depend on dbserver won't work
- Need alternative data access via NFS mount

## Anti-Patterns

- Using rbox's Rust ANLZ parser for DLP files (use pure Python parser)
- Overwriting SCUE-derived data with Pioneer data silently
- Assuming all Pioneer devices behave like CDJ-2000NXS2
- [TODO: Fill from project experience]
