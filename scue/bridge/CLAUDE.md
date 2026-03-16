# Layer 0 — Beat-Link Bridge

## What this layer does
Manages the beat-link Java subprocess that speaks the full Pro DJ Link protocol.
Streams typed JSON messages over a local WebSocket. Provides a Python adapter that
normalizes bridge data into Layer 1's internal types.

## Key dependencies
- Java 11+ (JRE must be installed on host)
- beat-link library (packaged as lib/beat-link-bridge.jar)

## Implementation rules
- The bridge JAR is a pre-built artifact. Do NOT compile Java source as part of SCUE's build.
- manager.py handles subprocess lifecycle: start, stop, restart on crash (with backoff).
- adapter.py normalizes BridgeMessage objects into Layer 1 types. Layer 1 does NOT import from bridge directly.
- fallback.py provides basic UDP parsing when the bridge is unavailable. Degraded mode only.
- All bridge message types are defined in messages.py as dataclasses.

## Testing
- Mock bridge data in tests/fixtures/bridge/
- Run: `python -m pytest tests/test_bridge/ -v`

## Output contract
See docs/CONTRACTS.md → "Layer 0 → Layer 1: BridgeMessage"

## Domain knowledge
For Pro DJ Link protocol details and beat-link API specifics, see docs/domains/pro-dj-link.md
For network configuration, see docs/domains/live-networking.md
