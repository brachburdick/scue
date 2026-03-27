# Section: ingestion

## Purpose
Track discovery and import from external sources: Pioneer USB drives (ANLZ file parsing, rekordbox XML/DB), local rekordbox libraries, and hardware-connected media. Responsible for scanning, parsing, and feeding tracks into `TrackStore`.

## Owned Paths
```
scue/layer1/scanner.py             — hardware scan orchestration (DLP-based)
scue/layer1/usb_scanner.py         — USB mount detection + ANLZ directory walking
scue/layer1/anlz_parser.py         — Pioneer ANLZ binary format parser
scue/layer1/rekordbox_scanner.py   — rekordbox XML/DB import
scue/layer1/reanalysis.py          — re-analysis pass orchestration
scue/api/scanner.py                — scanner REST endpoints
scue/api/usb.py                    — USB browse/import endpoints
scue/api/local_library.py          — local rekordbox library endpoints
config/usb.yaml                    — USB scanning paths
tests/test_layer1/test_scanner.py
tests/test_layer1/test_usb_scanner.py
tests/test_layer1/test_anlz_parser.py
tests/test_layer1/test_anlz_pssi.py
tests/test_layer1/test_rekordbox_scanner.py
```

## Incoming Inputs
- **From filesystem:** Pioneer USB exports (ANLZ files, `PIONEER/` directory structure, `exportLibrary.db`)
- **From filesystem:** Local rekordbox XML/DB files
- **From bridge section:** `DeviceInfo` (for hardware-connected media scanning via DLP)
- **From config:** `config/usb.yaml` (scan paths, mount points)

## Outgoing Outputs
- **To analysis section:** Discovered tracks added via `TrackStore.add()` / `TrackStore.update()`
- **Types:** `ScanResult`, `UsbDevice`, `AnlzData`, `PssiData`
- **REST API:** `/api/scanner/*`, `/api/usb/*`, `/api/local-library/*` endpoints
- **WebSocket:** Scan progress events broadcast to frontend

## Consumers
- **analysis section:** `TrackStore` receives discovered tracks
- **server section:** API routers in `scue/api/` expose scanner endpoints (co-owned — see note)
- **frontend section:** Ingestion page consumes scan progress and USB browse data

## Invariants
- Pioneer-sourced metadata is preserved verbatim — never transformed or normalized during import.
- ANLZ parser handles all known Pioneer binary formats (DAT, EXT, PSSI) without external libraries.
- USB scanner is idempotent — re-scanning the same device does not duplicate tracks.
- Rekordbox scanner handles both XML and DB formats.
- Scanner never imports from `detectors`, `strata`, `layer2-4`, or `bridge` implementation (only `DeviceInfo` type).

## Allowed Dependencies
- `scue.layer1.models` — `TrackAnalysis` (for building track records)
- `scue.layer1.storage` — `TrackStore` (to persist discovered tracks)
- `scue.bridge.adapter` — `DeviceInfo` type only (for hardware scan context)
- `scue.config` — USB config
- Python stdlib, `pyrekordbox`, `rbox`, `construct` (binary parsing)
- **NOT:** detectors, strata, layer2-4, main.py

## Co-ownership Note
The API routers (`scue/api/scanner.py`, `scue/api/usb.py`, `scue/api/local_library.py`) are co-owned with the **server** section. The server section owns the wiring (how routers are mounted in `main.py`), while the ingestion section owns the endpoint logic and request/response shapes. When in doubt, the ingestion section owns the "what" and the server section owns the "how."

## How to Verify
```bash
.venv/bin/python -m pytest tests/test_layer1/test_scanner.py tests/test_layer1/test_usb_scanner.py tests/test_layer1/test_anlz_parser.py tests/test_layer1/test_anlz_pssi.py tests/test_layer1/test_rekordbox_scanner.py -v
```
Tests use fixture files in `tests/fixtures/` — no real USB devices required.
