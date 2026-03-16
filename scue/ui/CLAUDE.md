# UI Layer

## What this layer does
Browser-based UI for SCUE. Two main panels:
1. **Live Decks** — real-time Pioneer deck status (CH1/CH2, BPM, beat position, flags)
2. **Track Analysis** — file upload, RGB waveform visualizer, section markers, JSON output

Also provides:
- WebSocket server for real-time Pioneer data → browser
- Preview mode (2D venue fixture grid, future: Layer 4 output visualization)
- Live control surface (future: route muting, manual cue triggers, palette switching)

## Key files
| File | Purpose |
|---|---|
| `websocket.py` | FastAPI WebSocket handlers + broadcast helpers |
| `static/index.html` | Main page layout |
| `static/style.css` | Dark theme styles |
| `static/app.js` | General app logic, upload flow, analysis display |
| `static/pioneer.js` | WebSocket client, deck panel updates, pioneer_status handling |
| `static/waveform.js` | `RGBWaveformRenderer` — Canvas rendering, section overlays, playback cursor |

## WebSocket message protocol (server → browser)
| type | When sent | Key fields |
|---|---|---|
| `full_state` | On WS connect | `decks: {player_num: DeckState}` |
| `deck_update` | On every Pioneer status packet | `channel`, `data: DeckState` |
| `pioneer_status` | Every 2s + on any deck update | `is_receiving`, `active_channels`, `packet_count` |
| `pong` | On "ping" from browser | — |

## Implementation rules
- **No framework** — plain HTML5/CSS/JS + Canvas. Do not introduce React, Vue, or similar without Brach's approval.
- WebSocket reconnects automatically on disconnect (see `pioneer.js`).
- The `pioneer_status.is_receiving` field (not WS connection state) drives the colored status badge.
  `is_receiving = (time since last Pioneer packet) < 5s`.
- Waveform data is the only large payload — it's computed once at analysis time and stored as JSON arrays.
- Future: layer4 abstract output can be visualized here in a 2D fixture grid canvas.

## Pioneer status badge states
- `"Server Offline"` (red) — WebSocket not connected
- `"Pioneer: No Data"` (yellow `.waiting`) — WS connected, no Pioneer packets in last 5s
- `"Pioneer: Live (CH X)"` (green `.connected`) — packets arriving, active channel shown
