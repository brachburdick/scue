/** WebSocket client — auto-reconnect, dispatches to Zustand stores.
 *
 * Per frontend/CLAUDE.md: Components never touch WS directly.
 * This module manages the connection and routes typed messages to stores.
 */

import type { WSMessage } from "../types";
import { useBridgeStore } from "../stores/bridgeStore";

const WS_URL = `ws://${window.location.hostname}:8000/ws`;

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let backoff = 1000; // ms, doubles on each failure up to 30s
const MAX_BACKOFF = 30000;

function dispatch(msg: WSMessage): void {
  switch (msg.type) {
    case "bridge_status":
      useBridgeStore.getState().setBridgeState(msg.payload);
      break;
    case "pioneer_status":
      useBridgeStore
        .getState()
        .setPioneerStatus(
          msg.payload.is_receiving,
          msg.payload.last_message_age_ms,
        );
      break;
  }
}

function onOpen(): void {
  backoff = 1000;
}

function onMessage(event: MessageEvent): void {
  try {
    const msg = JSON.parse(event.data) as WSMessage;
    dispatch(msg);
  } catch {
    // Ignore malformed messages
  }
}

function onClose(): void {
  ws = null;
  scheduleReconnect();
}

function onError(): void {
  ws?.close();
}

function scheduleReconnect(): void {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket();
  }, backoff);
  backoff = Math.min(backoff * 2, MAX_BACKOFF);
}

export function connectWebSocket(): void {
  if (ws) return;

  try {
    ws = new WebSocket(WS_URL);
    ws.onopen = onOpen;
    ws.onmessage = onMessage;
    ws.onclose = onClose;
    ws.onerror = onError;
  } catch {
    scheduleReconnect();
  }
}

export function disconnectWebSocket(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.onclose = null; // Prevent reconnect
    ws.close();
    ws = null;
  }
}
